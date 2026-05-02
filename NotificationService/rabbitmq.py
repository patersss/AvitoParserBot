import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from config import settings

logger = logging.getLogger(__name__)


class RabbitMQClient:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.exchange = None

    async def connect(self):
        for attempt in range(1, settings.startup_retry_attempts + 1):
            try:
                self.connection = await aio_pika.connect_robust(settings.rabbitmq_url)
                self.channel = await self.connection.channel()
                await self.channel.set_qos(prefetch_count=10)
                self.exchange = await self.channel.declare_exchange(
                    settings.notification_exchange,
                    aio_pika.ExchangeType.TOPIC,
                    durable=True,
                )
                logger.info("Connected to RabbitMQ")
                return
            except Exception:
                if attempt >= settings.startup_retry_attempts:
                    raise
                logger.warning("RabbitMQ is not ready; retrying in %s seconds", settings.startup_retry_delay_seconds)
                await asyncio.sleep(settings.startup_retry_delay_seconds)

    async def close(self):
        if self.connection:
            await self.connection.close()

    async def consume_notification_events(self, handler: Callable[[dict], Awaitable[None]]):
        if not self.channel or not self.exchange:
            raise RuntimeError("RabbitMQClient is not connected")

        queue = await self.channel.declare_queue(settings.notification_events_queue, durable=True)
        await queue.bind(self.exchange, routing_key=settings.listing_found_routing_key)
        await queue.bind(self.exchange, routing_key=settings.channel_upserted_routing_key)
        await queue.bind(self.exchange, routing_key=settings.channel_deleted_routing_key)

        async def on_message(message: AbstractIncomingMessage):
            try:
                payload = json.loads(message.body.decode("utf-8"))
            except json.JSONDecodeError:
                logger.exception("Invalid JSON in notification event. Rejecting without requeue.")
                await message.reject(requeue=False)
                return

            try:
                await handler(payload)
            except Exception:
                logger.exception("Failed to process notification event. Requeueing.")
                await message.reject(requeue=True)
                return

            await message.ack()

        await queue.consume(on_message)
        logger.info("Consuming notification events from queue %s", settings.notification_events_queue)
