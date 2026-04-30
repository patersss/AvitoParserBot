from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import ListingHistory, User
from app.schemas import ListingRead, Platform

router = APIRouter(prefix="/listings", tags=["listings"])


@router.get(
    "",
    response_model=list[ListingRead],
    summary="List current user's found listings",
    description=(
        "Returns all listings available to the authenticated user, optionally filtered by task id "
        "and platform. Data is populated from parserService `listing.found` RabbitMQ events."
    ),
    response_description="Current user's listings ordered by newest first.",
)
async def list_listings(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    task_id: UUID | None = None,
    platform: Platform | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ListingHistory]:
    conditions = [ListingHistory.user_id == user.id]
    if task_id:
        conditions.append(ListingHistory.task_id == task_id)
    if platform:
        conditions.append(ListingHistory.platform == platform)

    result = await db.execute(
        select(ListingHistory).where(*conditions).order_by(ListingHistory.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all())
