from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import ListingHistory, Task, User
from app.schemas import ListingRead, MessageResponse, Platform, TaskCreate, TaskRead, TaskUpdate
from app.services.rabbitmq import rabbitmq

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def get_user_task(db: AsyncSession, user: User, task_id: UUID, include_deleted: bool = False) -> Task:
    conditions = [Task.id == task_id, Task.user_id == user.id]
    if not include_deleted:
        conditions.append(Task.deleted_at.is_(None))
    result = await db.execute(select(Task).where(*conditions))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create parsing task",
    description=(
        "Creates a parsing task for the authenticated user and immediately publishes `task.upserted` "
        "to RabbitMQ so parserService can cache and run it. The task URL must match the selected platform."
    ),
    response_description="Created parsing task.",
)
async def create_task(
    payload: TaskCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Task:
    task = Task(
        user_id=user.id,
        name=payload.name,
        platform=payload.platform,
        url=payload.url,
        interval_minutes=payload.interval_minutes,
        end_date=payload.end_date,
        is_active=payload.is_active,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    await rabbitmq.publish_task_upserted(task, run_now=True)
    return task


@router.get(
    "",
    response_model=list[TaskRead],
    summary="List current user's tasks",
    description=(
        "Returns parsing tasks owned by the authenticated user. By default only active, non-deleted "
        "tasks are returned. Use `include_inactive=true` to include paused tasks."
    ),
    response_description="List of current user's tasks.",
)
async def list_tasks(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    include_inactive: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Task]:
    conditions = [Task.user_id == user.id, Task.deleted_at.is_(None)]
    if not include_inactive:
        conditions.append(Task.is_active.is_(True))
    result = await db.execute(
        select(Task).where(*conditions).order_by(Task.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all())


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    summary="Get task by id",
    description="Returns one non-deleted task if it belongs to the authenticated user.",
    response_description="Requested parsing task.",
)
async def get_task(
    task_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Task:
    return await get_user_task(db, user, task_id)


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    summary="Update parsing task",
    description=(
        "Updates editable task fields and publishes `task.upserted` to RabbitMQ. "
        "parserService uses this message to keep its `tasks_cache` up to date."
    ),
    response_description="Updated parsing task.",
)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Task:
    task = await get_user_task(db, user, task_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(task, key, value)
    await db.commit()
    await db.refresh(task)
    await rabbitmq.publish_task_upserted(task, run_now=False)
    return task


@router.post(
    "/{task_id}/refresh",
    response_model=MessageResponse,
    summary="Request immediate task refresh",
    description=(
        "Publishes the current task state as `task.upserted` with `next_run_at=now`. "
        "This asks parserService to parse the task on the nearest scheduler tick."
    ),
    response_description="Confirmation message.",
)
async def refresh_task(
    task_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    task = await get_user_task(db, user, task_id)
    await rabbitmq.publish_task_upserted(task, run_now=True)
    return MessageResponse(message="Task refresh has been requested")


@router.delete(
    "/{task_id}",
    response_model=MessageResponse,
    summary="Delete parsing task",
    description=(
        "Soft-deletes a task by setting `deleted_at` and `is_active=false`, then publishes "
        "`task.deleted` so parserService removes it from its cache."
    ),
    response_description="Confirmation message.",
)
async def delete_task(
    task_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    task = await get_user_task(db, user, task_id)
    task.is_active = False
    task.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    await rabbitmq.publish_task_deleted(task_id)
    return MessageResponse(message="Task has been deleted")


@router.get(
    "/{task_id}/listings",
    response_model=list[ListingRead],
    summary="List listings found for task",
    description=(
        "Returns listings saved for a user's task. Deleted tasks can still be queried here so the "
        "frontend may show historical results after task removal."
    ),
    response_description="Listings for the requested task.",
)
async def get_task_listings(
    task_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    platform: Platform | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ListingHistory]:
    await get_user_task(db, user, task_id, include_deleted=True)
    conditions = [ListingHistory.user_id == user.id, ListingHistory.task_id == task_id]
    if platform:
        conditions.append(ListingHistory.platform == platform)
    result = await db.execute(
        select(ListingHistory).where(*conditions).order_by(ListingHistory.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all())
