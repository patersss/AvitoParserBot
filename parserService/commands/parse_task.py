import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from messaging.rabbitmq import RabbitMQClient
from models.Post import FoundListing
from models.Task import TaskCache
from parsers.factory import ParserFactory
from repositories.listings import ListingRepository

logger = logging.getLogger(__name__)


class ParseTaskCommand:
    def __init__(self, session: AsyncSession, rabbitmq: RabbitMQClient, parser_factory: ParserFactory):
        self.session = session
        self.rabbitmq = rabbitmq
        self.parser_factory = parser_factory

    async def execute(self, task: TaskCache) -> list[FoundListing]:
        parser = self.parser_factory.get(task.platform)
        repository = ListingRepository(self.session)

        parsed_listings = await parser.parse(task)
        new_listings = await repository.save_new(task, parsed_listings)

        now = datetime.now(timezone.utc)
        task.last_run_at = now
        task.next_run_at = now + timedelta(minutes=task.interval_minutes)

        await self.session.commit()

        for listing in new_listings:
            await self.rabbitmq.publish_listing_found(self._notification_payload(task, listing))

        logger.info(
            "Task %s processed: %s parsed, %s new",
            task.task_id,
            len(parsed_listings),
            len(new_listings),
        )
        return new_listings

    def _notification_payload(self, task: TaskCache, listing: FoundListing) -> dict:
        return {
            "event_type": "listing.found",
            "source_service": "parsingService",
            "user_id": str(task.user_id),
            "task_id": str(task.task_id),
            "task_name": task.name,
            "listing": {
                "id": str(listing.id),
                "platform": listing.platform,
                "external_id": listing.external_id,
                "title": listing.title,
                "price": listing.price,
                "url": listing.url,
                "image_url": listing.image_url,
                "published_at": listing.published_at.isoformat() if listing.published_at else None,
                "created_at": listing.created_at.isoformat() if listing.created_at else None,
            },
        }
