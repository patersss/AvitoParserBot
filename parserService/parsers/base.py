from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from models.Task import TaskCache


@dataclass(frozen=True)
class ParsedListing:
    platform: str
    external_id: str
    title: str | None
    price: int | None
    url: str
    image_url: str | None = None
    published_at: datetime | None = None


class BaseParser(ABC):
    platform: str

    @abstractmethod
    async def parse(self, task: TaskCache) -> list[ParsedListing]:
        """Return listings from the platform page for the given task."""
