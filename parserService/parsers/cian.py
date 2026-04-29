import asyncio
import logging
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from config import settings
from models.Task import TaskCache
from parsers.base import BaseParser, ParsedListing

logger = logging.getLogger(__name__)


class CianParser(BaseParser):
    platform = "cian"

    def __init__(self, timeout_seconds: int = 20):
        self.timeout_seconds = timeout_seconds

    async def parse(self, task: TaskCache) -> list[ParsedListing]:
        return await asyncio.to_thread(self._parse_sync, task.url)

    def _parse_sync(self, url: str) -> list[ParsedListing]:
        response = requests.get(
            url,
            headers=self._headers(),
            cookies=settings.cian_cookies,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        listings = self._parse_offer_cards(soup)
        if not listings:
            listings = self._parse_embedded_json(soup)

        logger.info("Parsed %s Cian listings from %s", len(listings), url)
        return listings

    def _headers(self) -> dict[str, str]:
        return {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": "https://www.cian.ru/",
            "upgrade-insecure-requests": "1",
            "user-agent": settings.cian_user_agent,
        }

    def _parse_offer_cards(self, soup: BeautifulSoup) -> list[ParsedListing]:
        listings = []
        for card in soup.select("[data-testid='offer-card']"):
            link = card.select_one("[data-name='TitleComponent']") or card.select_one("a[href*='.cian.ru/']")
            href = link.get("href") if link else None
            absolute_url = self._normalize_url(href)
            external_id = self._id_from_url(absolute_url)
            if not external_id or not absolute_url:
                continue

            title = self._text(card.select_one("[data-mark='OfferTitle']")) or self._text(link)
            price = self._parse_price(self._text(card.select_one("[data-mark='MainPrice']")))
            image = card.select_one("img[src]")

            listings.append(
                ParsedListing(
                    platform=self.platform,
                    external_id=external_id,
                    title=title,
                    price=price,
                    url=absolute_url,
                    image_url=image.get("src") if image else None,
                )
            )

        return self._deduplicate(listings)

    def _parse_embedded_json(self, soup: BeautifulSoup) -> list[ParsedListing]:
        listings = []
        for script in soup.select("script"):
            text = script.string or script.get_text()
            if not text or "cian.ru" not in text:
                continue
            for raw_url in re.findall(r"https?://[^\"'\\\s]+?\.cian\.ru/(?:rent|sale)/[^\"'\\\s]+", text):
                absolute_url = self._normalize_url(raw_url)
                external_id = self._id_from_url(absolute_url)
                if not external_id or not absolute_url:
                    continue
                listings.append(
                    ParsedListing(
                        platform=self.platform,
                        external_id=external_id,
                        title=None,
                        price=None,
                        url=absolute_url,
                    )
                )

        return self._deduplicate(listings)

    def _id_from_url(self, url: str | None) -> str | None:
        if not url:
            return None
        path = urlsplit(url).path
        match = re.search(r"/(?:rent|sale)/[^/]+/(\d+)/?$", path)
        if match:
            return match.group(1)
        match = re.search(r"/(\d+)/?$", path)
        return match.group(1) if match else None

    def _normalize_url(self, url: str | None) -> str | None:
        if not url:
            return None
        absolute = urljoin("https://www.cian.ru", url)
        parts = urlsplit(absolute)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

    def _parse_price(self, value: str | None) -> int | None:
        if value is None:
            return None
        digits = re.sub(r"\D", "", value)
        return int(digits) if digits else None

    def _text(self, node) -> str | None:
        if not node:
            return None
        text = node.get_text(" ", strip=True)
        return text or None

    def _deduplicate(self, listings: list[ParsedListing]) -> list[ParsedListing]:
        seen = set()
        unique = []
        for listing in listings:
            if listing.external_id in seen:
                continue
            seen.add(listing.external_id)
            unique.append(listing)
        return unique
