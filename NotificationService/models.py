from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserChannelCache(Base):
    __tablename__ = "user_channels_cache"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint("type IN ('telegram', 'email', 'vk')", name="ck_user_channels_cache_type"),
        Index("ix_user_channels_cache_user_id_type", "user_id", "type"),
    )
