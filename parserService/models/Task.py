from sqlalchemy import Column, Integer, String, ForeignKey, Interval, DateTime, Boolean
from sqlalchemy.orm import relationship
from models.database import Base
from datetime import datetime, timedelta, timezone

class Task(Base):
    __tablename__ = 'task'

    id = Column(Integer, primary_key=True)
    app_user_id = Column(Integer, ForeignKey('app_user.id'))
    task_name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    interval = Column(Integer, nullable=False)
    next_run_at = Column(DateTime, default=lambda: datetime.now(timezone.utc) + timedelta(minutes=5))
    end_date = Column(DateTime)
    last_run_at = Column(DateTime)
    is_active = Column(Boolean, default=True)

    app_user = relationship("User", back_populates="tasks")
    posts = relationship("Post", back_populates="task", cascade="all, delete-orphan")