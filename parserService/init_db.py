import asyncio
import logging

from models.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def init_database():
    logger.info("Creating parser service tables...")
    await init_db()
    logger.info("Parser service tables are ready")


if __name__ == "__main__":
    asyncio.run(init_database())
