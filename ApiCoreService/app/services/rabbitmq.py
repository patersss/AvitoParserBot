import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.database import async_session
from app.models import ListingHistory, Task

logger = logging.getLogger(__name__)


def build_task_upserted_payload(task: Task, *, run_now: bool = False, now: datetime | None = None) -> dict:
    return {
        "event_type": "task.upserted",
        "source_service": "ApiCoreService",
        "payload": {
            "task_id": str(task.id),
            "user_id": str(task.user_id),
            "platform": task.platform,
            "url": task.url,
            "name": task.name,
            "interval_minutes": task.interval_minutes,
            "end_date": task.end_date.isoformat() if task.end_date else None,
            "is_active": task.is_active,
            "next_run_at": (now or datetime.now(timezone.utc)).isoformat() if run_now else None,
        },
    }


def build_task_deleted_payload(task_id: UUID) -> dict:
    return {
        "event_type": "task.deleted",
        "source_service": "ApiCoreService",
        "payload": {"task_id": str(task_id)},
    }


def listing_found_to_history_values(payload: dict, *, now: datetime | None = None) -> dict:
    listing = payload.get("listing") or {}
    return {
        "user_id": UUID(str(payload["user_id"])),
        "task_id": UUID(str(payload["task_id"])),
        "platform": listing.get("platform") or payload.get("platform"),
        "external_id": str(listing["external_id"]),
        "title": listing.get("title") or "",
        "price": listing.get("price"),
        "url": listing["url"],
        "image_url": listing.get("image_url"),
        "published_at": parse_datetime(listing.get("published_at")),
        "created_at": parse_datetime(listing.get("created_at")) or now or datetime.now(timezone.utc),
    }


def parse_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class RabbitMQClient:
    def __init__(self) -> None:
        self.connection: aio_pika.RobustConnection | None = None
        self.channel: aio_pika.RobustChannel | None = None
        self.notification_exchange: aio_pika.RobustExchange | None = None
        self._consumer_task: asyncio.Task | None = None

    async def connect(self) -> None:
        self.connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=10)
        self.notification_exchange = await self.channel.declare_exchange(
            settings.notification_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        await self.channel.declare_queue(settings.parser_task_events_queue, durable=True)
        logger.info("ApiCoreService connected to RabbitMQ")

    async def close(self) -> None:
        if self._consumer_task:
            self._consumer_task.cancel()
        if self.connection:
            await self.connection.close()

    async def publish_task_upserted(self, task: Task, *, run_now: bool = False) -> None:
        payload = build_task_upserted_payload(task, run_now=run_now)
        await self._publish_to_parser_queue(payload)

    async def publish_task_deleted(self, task_id: UUID) -> None:
        payload = build_task_deleted_payload(task_id)
        await self._publish_to_parser_queue(payload)

    async def publish_verification_code(self, email: str, code: str, expires_in_minutes: int) -> None:
        payload = {
            "event_type": "auth.email.verification",
            "source_service": "ApiCoreService",
            "email": email,
            "code": code,
            "expires_in_minutes": expires_in_minutes,
        }
        await self._publish_to_notification_exchange(payload, routing_key=settings.auth_email_verification_routing_key)

    async def publish_channel_upserted(self, channel, user_id) -> None:
        payload = {
            "event_type": "notification.channel.upserted",
            "source_service": "ApiCoreService",
            "user_id": str(user_id),
            "channel": {
                "id": str(channel.id),
                "type": channel.type,
                "config": channel.config,
                "is_active": channel.is_active,
            },
        }
        await self._publish_to_notification_exchange(
            payload, routing_key=settings.notification_channel_upserted_routing_key
        )

    async def publish_channel_deleted(self, channel_id, user_id, channel_type: str) -> None:
        payload = {
            "event_type": "notification.channel.deleted",
            "source_service": "ApiCoreService",
            "user_id": str(user_id),
            "channel_id": str(channel_id),
            "type": channel_type,
        }
        await self._publish_to_notification_exchange(
            payload, routing_key=settings.notification_channel_deleted_routing_key
        )

    async def publish_password_reset(self, email: str, reset_link: str) -> None:
        payload = {
            "event_type": "auth.email.password_reset",
            "source_service": "ApiCoreService",
            "email": email,
            "reset_link": reset_link,
        }
        await self._publish_to_notification_exchange(payload, routing_key=settings.auth_email_reset_routing_key)

    async def _publish_to_parser_queue(self, payload: dict) -> None:
        if not self.channel:
            raise RuntimeError("RabbitMQ is not connected")
        message = aio_pika.Message(
            body=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self.channel.default_exchange.publish(message, routing_key=settings.parser_task_events_queue)

    async def _publish_to_notification_exchange(self, payload: dict, *, routing_key: str) -> None:
        if not self.notification_exchange:
            raise RuntimeError("RabbitMQ is not connected")
        message = aio_pika.Message(
            body=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self.notification_exchange.publish(message, routing_key=routing_key)

    async def start_listing_consumer(self) -> None:
        if not self.channel or not self.notification_exchange:
            raise RuntimeError("RabbitMQ is not connected")

        queue = await self.channel.declare_queue(settings.api_listing_found_queue, durable=True)
        await queue.bind(self.notification_exchange, routing_key=settings.listing_found_routing_key)
        await queue.consume(self._on_listing_found)
        logger.info("ApiCoreService consumes listing.found events from queue %s", settings.api_listing_found_queue)

    async def _on_listing_found(self, message: AbstractIncomingMessage) -> None:
        try:
            payload = json.loads(message.body.decode("utf-8"))
        except json.JSONDecodeError:
            logger.exception("Invalid listing.found JSON. Rejecting message.")
            await message.reject(requeue=False)
            return

        try:
            await self._save_listing(payload)
        except Exception:
            logger.exception("Failed to persist listing.found. Requeueing message.")
            await message.reject(requeue=True)
            return

        await message.ack()

    async def _save_listing(self, payload: dict) -> None:
        event_type = payload.get("event_type")
        now = datetime.now(timezone.utc)

        if event_type == "listings.batch_found":
            rows = [
                listing_found_to_history_values({**payload, "listing": listing}, now=now)
                for listing in (payload.get("listings") or [])
            ]
        else:
            rows = [listing_found_to_history_values(payload, now=now)]

        if not rows:
            return

        async with async_session() as session:
            for values in rows:
                statement = (
                    insert(ListingHistory)
                    .values(**values)
                    .on_conflict_do_nothing(index_elements=["task_id", "platform", "external_id"])
                )
                await session.execute(statement)
            await session.commit()


rabbitmq = RabbitMQClient()
