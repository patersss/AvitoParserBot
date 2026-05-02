import asyncio
import logging

from database import init_db
from notifiers import EmailNotifier, TelegramNotifier
from rabbitmq import RabbitMQClient
from repositories import ChannelRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self):
        self.rabbitmq = RabbitMQClient()
        self.channels = ChannelRepository()
        self.telegram = TelegramNotifier()
        self.email = EmailNotifier()

    async def start(self):
        await init_db()
        await self.rabbitmq.connect()
        await self.rabbitmq.consume_notification_events(self.handle_event)
        logger.info("NotificationService started")
        await asyncio.Event().wait()

    async def stop(self):
        await self.rabbitmq.close()
        await self.telegram.close()

    async def handle_event(self, payload: dict):
        event_type = payload.get("event_type") or payload.get("type")
        if event_type == "listing.found":
            await self._handle_listing_found(payload)
            return
        if event_type in {"notification_channel.upserted", "notification.channel.upserted"}:
            await self._handle_channel_upserted(payload)
            return
        if event_type in {"notification_channel.deleted", "notification.channel.deleted"}:
            await self._handle_channel_deleted(payload)
            return
        logger.info("Ignoring unsupported notification event type: %s", event_type)

    async def _handle_channel_upserted(self, payload: dict):
        user_id = payload.get("user_id")
        channel = payload.get("channel") or payload.get("payload") or {}
        if not user_id or not channel:
            raise ValueError("notification_channel.upserted requires user_id and channel")

        channel_type = channel["type"]
        config = channel.get("config") or {}
        is_active = bool(channel.get("is_active", True))
        await self.channels.upsert_channel(user_id, channel_type, config, is_active)
        logger.info("Notification channel cached: user_id=%s type=%s active=%s", user_id, channel_type, is_active)

    async def _handle_channel_deleted(self, payload: dict):
        data = payload.get("payload") or payload
        user_id = data.get("user_id")
        channel_type = data.get("type") or data.get("channel_type")
        if not user_id or not channel_type:
            raise ValueError("notification_channel.deleted requires user_id and type")

        await self.channels.disable_channel(user_id, channel_type)
        logger.info("Notification channel disabled: user_id=%s type=%s", user_id, channel_type)

    async def _handle_listing_found(self, payload: dict):
        user_id = payload.get("user_id")
        if not user_id:
            raise ValueError("listing.found requires user_id")

        channels = await self.channels.get_active_channels(user_id)
        if not channels:
            logger.info("No active notification channels for user %s", user_id)
            return

        for channel in channels:
            if channel.type == "telegram":
                await self.telegram.send_listing(channel.config, payload)
            elif channel.type == "email":
                await self.email.send_listing(channel.config, payload)
            else:
                logger.info("Unsupported channel type %s for user %s", channel.type, user_id)


async def main():
    service = NotificationService()
    try:
        await service.start()
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
