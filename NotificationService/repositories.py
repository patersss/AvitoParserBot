from uuid import UUID

from sqlalchemy import select

from database import async_session
from models import UserChannelCache


class ChannelRepository:
    async def upsert_channel(self, user_id: str, channel_type: str, config: dict, is_active: bool = True) -> UserChannelCache:
        user_uuid = UUID(str(user_id))
        async with async_session() as session:
            channel = await session.get(UserChannelCache, {"user_id": user_uuid, "type": channel_type})
            if not channel:
                channel = UserChannelCache(user_id=user_uuid, type=channel_type, config=config, is_active=is_active)
                session.add(channel)
            else:
                channel.config = config
                channel.is_active = is_active
            await session.commit()
            await session.refresh(channel)
            return channel

    async def disable_channel(self, user_id: str, channel_type: str) -> None:
        user_uuid = UUID(str(user_id))
        async with async_session() as session:
            channel = await session.get(UserChannelCache, {"user_id": user_uuid, "type": channel_type})
            if channel:
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
