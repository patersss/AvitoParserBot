from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from models.database import Base


class FoundListing(Base):
    __tablename__ = "found_listings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks_cache.task_id", ondelete="CASCADE"), nullable=False)
    platform = Column(String(30), nullable=False)
    external_id = Column(String(150), nullable=False)
    title = Column(Text)
    price = Column(BigInteger)
    url = Column(Text, nullable=False)
    image_url = Column(Text)
    published_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    task = relationship("TaskCache", back_populates="listings")

    __table_args__ = (
        UniqueConstraint("task_id", "platform", "external_id", name="uix_found_listing_task_platform_external"),
        CheckConstraint("platform IN ('avito', 'cian', 'youla')", name="ck_found_listings_platform"),
    )


# Backward-compatible name for older imports inside parserService.
Post = FoundListing
