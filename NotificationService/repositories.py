from uuid import UUID

from sqlalchemy import select

from database import async_session
from models import UserChannelCache


class ChannelRepository:
    async def upsert_channel_by_id(
        self,
        channel_id: str,
        user_id: str,
        channel_type: str,
        config: dict,
        is_active: bool = True,
    ) -> UserChannelCache:
        channel_uuid = UUID(str(channel_id))
        user_uuid = UUID(str(user_id))
        async with async_session() as session:
            channel = await session.get(UserChannelCache, channel_uuid)
            if not channel:
                channel = UserChannelCache(
                    id=channel_uuid,
                    user_id=user_uuid,
                    type=channel_type,
                    config=config,
                    is_active=is_active,
                )
                session.add(channel)
            else:
                channel.config = config
                channel.is_active = is_active
            await session.commit()
            await session.refresh(channel)
            return channel

    async def upsert_channel(
        self,
        user_id: str,
        channel_type: str,
        config: dict,
        is_active: bool = True,
    ) -> UserChannelCache:
        """Fallback upsert by (user_id, type) for services that do not send a channel_id (e.g. BotService)."""
        user_uuid = UUID(str(user_id))
        async with async_session() as session:
            result = await session.execute(
                select(UserChannelCache).where(
                    UserChannelCache.user_id == user_uuid,
                    UserChannelCache.type == channel_type,
                )
            )
            channel = result.scalars().first()
            if not channel:
                channel = UserChannelCache(
                    user_id=user_uuid,
                    type=channel_type,
                    config=config,
                    is_active=is_active,
                )
                session.add(channel)
            else:
                channel.config = config
                channel.is_active = is_active
            await session.commit()
            await session.refresh(channel)
            return channel

    async def disable_channel_by_id(self, channel_id: str) -> None:
        channel_uuid = UUID(str(channel_id))
        async with async_session() as session:
            channel = await session.get(UserChannelCache, channel_uuid)
            if channel:
                channel.is_active = False
                await session.commit()

    async def disable_channel(self, user_id: str, channel_type: str) -> None:
        """Fallback disable by (user_id, type) for services that do not send a channel_id."""
        user_uuid = UUID(str(user_id))
        async with async_session() as session:
            result = await session.execute(
                select(UserChannelCache).where(
                    UserChannelCache.user_id == user_uuid,
                    UserChannelCache.type == channel_type,
                )
            )
            for channel in result.scalars().all():
                channel.is_active = False
            await session.commit()

    async def get_active_channels(self, user_id: str) -> list[UserChannelCache]:
        user_uuid = UUID(str(user_id))
        async with async_session() as session:
            result = await session.execute(
                select(UserChannelCache).where(
                    UserChannelCache.user_id == user_uuid,
                    UserChannelCache.is_active.is_(True),
                )
            )
            return list(result.scalars().all())
