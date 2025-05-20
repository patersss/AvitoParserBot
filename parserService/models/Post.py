from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from models.database import Base
from datetime import datetime, timezone

class Post(Base):
    __tablename__ = 'post'

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('task.id'))
    post_id = Column(String, nullable=False)
    title = Column(String)
    url = Column(String, nullable=False)
    price = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    task = relationship("Task", back_populates="posts")

    __table_args__ = (UniqueConstraint('task_id', 'post_id', name='uix_task_post'),)