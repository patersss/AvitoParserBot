import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, or_, select

from commands.parse_task import ParseTaskCommand
from config import settings
from messaging.rabbitmq import RabbitMQClient
from models.Task import TaskCache
from models.database import async_session, init_db
from parsers.factory import ParserFactory
from init_db import init_database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("scheduler.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class TaskEventHandler:
    async def handle(self, payload: dict):
        event_type = payload.get("event_type") or payload.get("type") or "task.upserted"
        data = payload.get("payload") or payload.get("task") or payload

        if event_type in {"task.deleted", "task.delete", "delete"}:
            await self._delete_task(data)
            return

        await self._upsert_task(data)

    async def _upsert_task(self, data: dict):
        task_id = self._required_uuid(data, "task_id", "id")
        user_id = self._required_uuid(data, "user_id")
        platform = str(data["platform"]).lower()
        interval_minutes = int(data.get("interval_minutes") or data.get("interval") or 30)

        async with async_session() as session:
            task = await session.get(TaskCache, task_id)
            if not task:
                task = TaskCache(task_id=task_id)
                session.add(task)

            task.user_id = user_id
            task.platform = platform
            task.url = data["url"]
            task.name = data.get("name") or data.get("task_name")
            task.interval_minutes = interval_minutes
            task.end_date = self._parse_datetime(data.get("end_date"))
            task.is_active = bool(data.get("is_active", True))
            task.next_run_at = self._parse_datetime(data.get("next_run_at")) or datetime.now(timezone.utc)

            await session.commit()
            logger.info("Task %s cached/updated for platform %s", task_id, platform)

    async def _delete_task(self, data: dict):
        task_id = self._required_uuid(data, "task_id", "id")
        async with async_session() as session:
            await session.execute(delete(TaskCache).where(TaskCache.task_id == task_id))
            await session.commit()
            logger.info("Task %s deleted from cache", task_id)

    def _required_uuid(self, data: dict, *keys: str) -> UUID:
        for key in keys:
            if data.get(key):
                return UUID(str(data[key]))
        raise ValueError(f"Missing required UUID field. Expected one of: {', '.join(keys)}")

    def _parse_datetime(self, value) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class TaskScheduler:
    def __init__(self, rabbitmq: RabbitMQClient):
        self.rabbitmq = rabbitmq
        self.parser_factory = ParserFactory()
        self.running_tasks: set[UUID] = set()

    async def get_tasks_to_run(self) -> list[TaskCache]:
        now = datetime.now(timezone.utc)
        supported_platforms = sorted(self.parser_factory.supported_platforms)
        async with async_session() as session:
            result = await session.execute(
                select(TaskCache).where(
                    TaskCache.is_active.is_(True),
                    TaskCache.platform.in_(supported_platforms),
                    TaskCache.next_run_at <= now,
                    or_(TaskCache.end_date.is_(None), TaskCache.end_date >= now),
                )
                .order_by(TaskCache.next_run_at.asc())
                .limit(settings.scheduler_batch_size)
            )
            return list(result.scalars().all())

    async def run_task(self, task_id: UUID):
        if task_id in self.running_tasks:
            logger.info("Task %s is already running", task_id)
            return

        self.running_tasks.add(task_id)
        try:
            async with async_session() as session:
                task = await session.get(TaskCache, task_id)
                if not task or not task.is_active:
                    return
                command = ParseTaskCommand(session, self.rabbitmq, self.parser_factory)
                await command.execute(task)
        except Exception:
            logger.exception("Failed to process task %s", task_id)
        finally:
            self.running_tasks.remove(task_id)

    async def run(self):
        logger.info("Parser scheduler started")
        while True:
            tasks = await self.get_tasks_to_run()
            if tasks:
                await asyncio.gather(*(self.run_task(task.task_id) for task in tasks))
            await asyncio.sleep(settings.scheduler_tick_seconds)


async def main():
    await init_database()

    rabbitmq = RabbitMQClient()
    await rabbitmq.connect()

    task_events = TaskEventHandler()
    await rabbitmq.consume_task_events(task_events.handle)

    scheduler = TaskScheduler(rabbitmq)
    try:
        await scheduler.run()
    finally:
        await rabbitmq.close()


if __name__ == "__main__":
    asyncio.run(main())
