import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
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

        is_first_run = task.last_run_at is None

        parsed_listings = await parser.parse(task)
        new_listings = await repository.save_new(task, parsed_listings)

        now = datetime.now(timezone.utc)
        task.last_run_at = now
        task.next_run_at = now + timedelta(minutes=task.interval_minutes)

        await self.session.commit()

        listings_to_notify = new_listings[:settings.first_run_notify_limit] if is_first_run else new_listings

        if listings_to_notify:
            await self.rabbitmq.publish_listings_batch(self._batch_payload(task, listings_to_notify))

        logger.info(
            "Task %s processed: %s parsed, %s new, %s notified%s",
            task.task_id,
            len(parsed_listings),
            len(new_listings),
            len(listings_to_notify),
            f" (first run, capped at {settings.first_run_notify_limit})" if is_first_run else "",
        )
        return new_listings

    def _batch_payload(self, task: TaskCache, listings: list[FoundListing]) -> dict:
        return {
            "event_type": "listings.batch_found",
            "source_service": "parsingService",
            "user_id": str(task.user_id),
            "task_id": str(task.task_id),
            "task_name": task.name,
            "listings": [self._listing_data(listing) for listing in listings],
        }

    def _listing_data(self, listing: FoundListing) -> dict:
        return {
            "id": str(listing.id),
            "platform": listing.platform,
            "external_id": listing.external_id,
            "title": listing.title,
            "price": listing.price,
            "url": listing.url,
            "image_url": listing.image_url,
            "published_at": listing.published_at.isoformat() if listing.published_at else None,
            "created_at": listing.created_at.isoformat() if listing.created_at else None,
        }
