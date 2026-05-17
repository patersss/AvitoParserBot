import asyncio
import logging

from database import init_db
from notifiers import EmailNotifier, TelegramNotifier, VKNotifier
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
        self.vk = VKNotifier()

    async def start(self):
        await init_db()
        await self.rabbitmq.connect()
        await self.rabbitmq.consume_notification_events(self.handle_event)
        logger.info("NotificationService started")
        await asyncio.Event().wait()

    async def stop(self):
        await self.rabbitmq.close()
        await self.telegram.close()
        await self.vk.close()

    async def handle_event(self, payload: dict):
        event_type = payload.get("event_type") or payload.get("type")
        if event_type == "listings.batch_found":
            await self._handle_listings_batch_found(payload)
            return
        if event_type == "listing.found":
            await self._handle_listing_found(payload)
            return
        if event_type in {"notification_channel.upserted", "notification.channel.upserted"}:
            await self._handle_channel_upserted(payload)
            return
        if event_type in {"notification_channel.deleted", "notification.channel.deleted"}:
            await self._handle_channel_deleted(payload)
            return
        if event_type == "auth.email.verification":
            await self._handle_verification_code(payload)
            return
        if event_type == "auth.email.password_reset":
            await self._handle_password_reset(payload)
            return
        logger.info("Ignoring unsupported notification event type: %s", event_type)

    async def _handle_channel_upserted(self, payload: dict):
        user_id = payload.get("user_id")
        channel = payload.get("channel") or payload.get("payload") or {}
        if not user_id or not channel:
            raise ValueError("notification_channel.upserted requires user_id and channel")

        channel_id = channel.get("id") or channel.get("channel_id")
        channel_type = channel["type"]
        config = channel.get("config") or {}
        is_active = bool(channel.get("is_active", True))

        if channel_id:
            await self.channels.upsert_channel_by_id(channel_id, user_id, channel_type, config, is_active)
        else:
            await self.channels.upsert_channel(user_id, channel_type, config, is_active)
        logger.info("Notification channel cached: user_id=%s type=%s active=%s", user_id, channel_type, is_active)

    async def _handle_channel_deleted(self, payload: dict):
        data = payload.get("payload") or payload
        user_id = data.get("user_id")
        channel_id = data.get("channel_id") or data.get("id")
        channel_type = data.get("type") or data.get("channel_type")

        if channel_id:
            await self.channels.disable_channel_by_id(channel_id)
        elif user_id and channel_type:
            await self.channels.disable_channel(user_id, channel_type)
        else:
            raise ValueError("notification_channel.deleted requires channel_id or (user_id + type)")
        logger.info("Notification channel disabled: channel_id=%s user_id=%s type=%s", channel_id, user_id, channel_type)

    async def _handle_verification_code(self, payload: dict):
        email = payload.get("email")
        code = payload.get("code")
        expires_in = int(payload.get("expires_in_minutes", 10))
        if not email or not code:
            raise ValueError("auth.email.verification requires 'email' and 'code'")
        await self.email.send_verification_code(email, str(code), expires_in)

    async def _handle_password_reset(self, payload: dict):
        email = payload.get("email")
        reset_link = payload.get("reset_link")
        if not email or not reset_link:
            raise ValueError("auth.email.password_reset requires 'email' and 'reset_link'")
        await self.email.send_password_reset(email, reset_link)

    async def _handle_listings_batch_found(self, payload: dict):
        user_id = payload.get("user_id")
        if not user_id:
            raise ValueError("listings.batch_found requires user_id")

        listings = payload.get("listings") or []
        if not listings:
            logger.info("listings.batch_found with empty listings list, skipping")
            return

        channels = await self.channels.get_active_channels(user_id)
        if not channels:
            logger.info("No active notification channels for user %s", user_id)
            return

        for channel in channels:
            if channel.type == "telegram":
                for listing_data in listings:
                    single_payload = {**payload, "listing": listing_data}
                    await self.telegram.send_listing(channel.config, single_payload)
            elif channel.type == "email":
                await self.email.send_listings_batch(channel.config, payload)
            elif channel.type == "vk":
                await self.vk.send_listings_batch(channel.config, payload)
            else:
                logger.info("Unsupported channel type %s for user %s", channel.type, user_id)

    async def _handle_listing_found(self, payload: dict):
        """Backward-compatible handler for single listing.found events."""
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
            elif channel.type == "vk":
                await self.vk.send_listing(channel.config, payload)
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
