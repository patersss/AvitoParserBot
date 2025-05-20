import asyncio
import logging
from models.database import engine, Base
from models.User import User
from models.Task import Task
from models.Post import Post

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def init_database():
    try:
        logger.info("Начинаем инициализацию базы данных...")

        # Создаем таблицы
        async with engine.begin() as conn:
            logger.info("Создаем таблицы...")
            await conn.run_sync(Base.metadata.drop_all)  # Удаляем существующие таблицы
            await conn.run_sync(Base.metadata.create_all)  # Создаем таблицы заново
            logger.info("Таблицы успешно созданы")

        logger.info("Инициализация базы данных завершена успешно")

    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        asyncio.run(init_database())
    except Exception as e:
        logger.error(f"Критическая ошибка: {str(e)}", exc_info=True)
        exit(1)
