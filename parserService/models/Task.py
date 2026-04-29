from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from models.database import Base


class TaskCache(Base):
    __tablename__ = "tasks_cache"

    task_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    platform = Column(String(30), nullable=False)
    url = Column(Text, nullable=False)
    name = Column(String(150))
    interval_minutes = Column(Integer, nullable=False)
    end_date = Column(DateTime(timezone=True))
    is_active = Column(Boolean, nullable=False, default=True)
    next_run_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    last_run_at = Column(DateTime(timezone=True))

    listings = relationship(
        "FoundListing",
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("platform IN ('avito', 'cian', 'youla')", name="ck_tasks_cache_platform"),
        CheckConstraint("interval_minutes > 0", name="ck_tasks_cache_interval"),
    )


# Backward-compatible name for older imports inside parserService.
Task = TaskCache
