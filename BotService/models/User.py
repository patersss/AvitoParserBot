from sqlalchemy import Column, Integer, BigInteger, String
from sqlalchemy.orm import relationship
from models.database import Base


class User(Base):
    __tablename__ = 'app_user'

    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, unique=True, nullable=False)
    name = Column(String)

    tasks = relationship("Task", back_populates="app_user", cascade="all, delete-orphan")
