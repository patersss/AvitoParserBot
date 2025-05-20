from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

# Получаем параметры подключения из переменных окружения
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "admin")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "avito_parser")

# Создаем URL для подключения к базе данных (асинхронный)
DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Создаем асинхронный движок SQLAlchemy
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # Включаем логирование SQL-запросов
    pool_size=20,  # Размер пула соединений
    max_overflow=10,  # Максимальное количество дополнительных соединений
    pool_timeout=30,  # Таймаут ожидания соединения из пула
    pool_recycle=1800,  # Переподключение каждые 30 минут
)

# Создаем фабрику асинхронных сессий
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Создаем базовый класс для моделей
Base = declarative_base()

async def init_db():
    """Инициализация базы данных - создание всех таблиц"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    """Получение асинхронной сессии базы данных"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()