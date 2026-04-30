from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models import ListingHistory, Task, User
from app.schemas import AdminBanRequest, ListingRead, MessageResponse, TaskRead, UserRead, UserStatus
from app.services.rabbitmq import rabbitmq

router = APIRouter(prefix="/admin", tags=["admin"])


def ensure_can_manage_user(admin: User, target: User) -> None:
    if target.user_role == "superadmin" and admin.user_role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only superadmin can manage superadmin")


@router.get(
    "/users",
    response_model=list[UserRead],
    summary="List users",
    description=(
        "Admin-only endpoint for browsing users. Supports optional status filtering and pagination. "
        "Only users with role `admin` or `superadmin` may call it."
    ),
    response_description="Users ordered by newest first.",
)
async def list_users(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: UserStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[User]:
    conditions = []
    if status_filter:
        conditions.append(User.status == status_filter)
    result = await db.execute(select(User).where(*conditions).order_by(User.created_at.desc()).limit(limit).offset(offset))
    return list(result.scalars().all())


@router.get(
    "/users/{user_id}",
    response_model=UserRead,
    summary="Get user by id",
    description="Admin-only endpoint that returns a user profile by id.",
    response_description="Requested user profile.",
)
async def get_user(
    user_id: UUID,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch(
    "/users/{user_id}/ban",
    response_model=MessageResponse,
    summary="Ban user",
    description=(
        "Admin-only endpoint that changes user status to `banned`. A normal admin cannot manage "
        "a `superadmin`; only a `superadmin` can do that."
    ),
    response_description="Confirmation message.",
)
async def ban_user(
    user_id: UUID,
    payload: AdminBanRequest,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    ensure_can_manage_user(admin, user)
    user.status = "banned"
    await db.commit()
    return MessageResponse(message="User has been banned")


@router.patch(
    "/users/{user_id}/unban",
    response_model=MessageResponse,
    summary="Unban user",
    description=(
        "Admin-only endpoint that changes user status back to `active`. A normal admin cannot manage "
        "a `superadmin`; only a `superadmin` can do that."
    ),
    response_description="Confirmation message.",
)
async def unban_user(
    user_id: UUID,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    ensure_can_manage_user(admin, user)
    user.status = "active"
    await db.commit()
    return MessageResponse(message="User has been unbanned")


@router.get(
    "/users/{user_id}/tasks",
    response_model=list[TaskRead],
    summary="List user's tasks",
    description="Admin-only endpoint for inspecting tasks owned by any user.",
    response_description="Requested user's tasks.",
)
async def list_user_tasks(
    user_id: UUID,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    include_deleted: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Task]:
    conditions = [Task.user_id == user_id]
    if not include_deleted:
        conditions.append(Task.deleted_at.is_(None))
    result = await db.execute(select(Task).where(*conditions).order_by(Task.created_at.desc()).limit(limit).offset(offset))
    return list(result.scalars().all())


@router.delete(
    "/tasks/{task_id}",
    response_model=MessageResponse,
    summary="Delete any task",
    description=(
        "Admin-only endpoint that soft-deletes any task and publishes `task.deleted` to parserService. "
        "Use it for moderation or support cases."
    ),
    response_description="Confirmation message.",
)
async def delete_task(
    task_id: UUID,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    task.is_active = False
    task.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    await rabbitmq.publish_task_deleted(task_id)
    return MessageResponse(message="Task has been deleted")


@router.get(
    "/tasks/{task_id}/listings",
    response_model=list[ListingRead],
    summary="List listings for any task",
    description="Admin-only endpoint for inspecting listings found for any parsing task.",
    response_description="Listings for the requested task.",
)
async def get_task_listings(
    task_id: UUID,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ListingHistory]:
    result = await db.execute(
        select(ListingHistory)
        .where(ListingHistory.task_id == task_id)
        .order_by(ListingHistory.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())
