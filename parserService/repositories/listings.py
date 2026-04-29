from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.Post import FoundListing
from models.Task import TaskCache
from parsers.base import ParsedListing


class ListingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_existing_external_ids(self, task: TaskCache) -> set[str]:
        result = await self.session.execute(
            select(FoundListing.external_id).where(
                FoundListing.task_id == task.task_id,
                FoundListing.platform == task.platform,
            )
        )
        return set(result.scalars().all())

    async def save_new(self, task: TaskCache, listings: list[ParsedListing]) -> list[FoundListing]:
        existing_ids = await self.get_existing_external_ids(task)
        new_rows = []

        for listing in listings:
            if listing.external_id in existing_ids:
                continue
            row = FoundListing(
                user_id=task.user_id,
                task_id=task.task_id,
                platform=listing.platform,
                external_id=listing.external_id,
                title=listing.title,
                price=listing.price,
                url=listing.url,
                image_url=listing.image_url,
                published_at=listing.published_at,
            )
            self.session.add(row)
            new_rows.append(row)
            existing_ids.add(listing.external_id)

        if new_rows:
            await self.session.flush()

        return new_rows
