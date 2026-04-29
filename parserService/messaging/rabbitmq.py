import json
import logging
from typing import Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from config import settings

logger = logging.getLogger(__name__)


class RabbitMQClient:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.notification_exchange = None

    async def connect(self):
        self.connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=10)
        self.notification_exchange = await self.channel.declare_exchange(
            settings.notification_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        await self.channel.declare_queue(settings.task_events_queue, durable=True)
        logger.info("Connected to RabbitMQ")

    async def close(self):
        if self.connection:
            await self.connection.close()

    async def publish_listing_found(self, payload: dict):
        if not self.notification_exchange:
            raise RuntimeError("RabbitMQClient is not connected")

        message = aio_pika.Message(
            body=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self.notification_exchange.publish(message, routing_key=settings.listing_found_routing_key)

    async def consume_task_events(self, handler: Callable[[dict], Awaitable[None]]):
        if not self.channel:
            raise RuntimeError("RabbitMQClient is not connected")

        queue = await self.channel.declare_queue(settings.task_events_queue, durable=True)

        async def on_message(message: AbstractIncomingMessage):
            async with message.process(requeue=True):
                payload = json.loads(message.body.decode("utf-8"))
                await handler(payload)

        await queue.consume(on_message)
        logger.info("Consuming task events from queue %s", settings.task_events_queue)
