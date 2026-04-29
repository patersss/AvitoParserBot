import asyncio
import json
import logging
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from config import settings
from models.Task import TaskCache
from parsers.base import BaseParser, ParsedListing

logger = logging.getLogger(__name__)


class AvitoParser(BaseParser):
    platform = "avito"

    def __init__(self, timeout_seconds: int = 20):
        self.timeout_seconds = timeout_seconds

    async def parse(self, task: TaskCache) -> list[ParsedListing]:
        return await asyncio.to_thread(self._parse_sync, task.url)

    def _parse_sync(self, url: str) -> list[ParsedListing]:
        response = requests.get(
            url,
            headers=self._headers(),
            cookies=settings.avito_cookies,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        listings = self._parse_items(soup)
        if not listings:
            listings = self._parse_next_data(soup)

        logger.info("Parsed %s Avito listings from %s", len(listings), url)
        return listings

    def _headers(self) -> dict[str, str]:
        return {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": "https://www.avito.ru/",
            "upgrade-insecure-requests": "1",
            "user-agent": settings.avito_user_agent,
        }

    def _parse_items(self, soup: BeautifulSoup) -> list[ParsedListing]:
        listings = []
        for item in soup.select("[data-marker='item']"):
            link = item.select_one("[data-marker='item-title']")
            href = link.get("href") if link else None
            absolute_url = self._normalize_url(href)
            external_id = self._extract_external_id(item, absolute_url)
            if not external_id or not absolute_url:
                continue

            title = self._text(link) or self._text(item.select_one("[itemprop='name']"))
            price_node = item.select_one("[itemprop='price']")
            price = self._parse_price(price_node.get("content") if price_node else self._text(price_node))
            image = item.select_one("img")

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

    def _parse_next_data(self, soup: BeautifulSoup) -> list[ParsedListing]:
        script = soup.select_one("script#__NEXT_DATA__")
        if not script or not script.string:
            return []

        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            return []

        listings = []
        for item in self._walk_dicts(data):
            url = item.get("url") or item.get("uri") or item.get("href")
            absolute_url = self._normalize_url(url)
            external_id = str(item.get("id") or item.get("itemId") or self._id_from_url(absolute_url) or "")
            title = item.get("title") or item.get("name")
            if not external_id or not absolute_url or not title:
                continue

            price = item.get("price") or item.get("priceValue")
            if isinstance(price, dict):
                price = price.get("value") or price.get("current")

            image_url = None
            images = item.get("images") or item.get("image")
            if isinstance(images, list) and images:
                first = images[0]
                image_url = first.get("url") if isinstance(first, dict) else str(first)
            elif isinstance(images, dict):
                image_url = images.get("url")

            listings.append(
                ParsedListing(
                    platform=self.platform,
                    external_id=external_id,
                    title=str(title),
                    price=self._parse_price(price),
                    url=absolute_url,
                    image_url=image_url,
                )
            )

        return self._deduplicate(listings)

    def _extract_external_id(self, item, url: str | None) -> str | None:
        marker = item.get("data-item-id") or item.get("id")
        if marker:
            match = re.search(r"\d+", str(marker))
            if match:
                return match.group(0)
        return self._id_from_url(url)

    def _id_from_url(self, url: str | None) -> str | None:
        if not url:
            return None
        path = urlsplit(url).path
        match = re.search(r"_(\d+)$", path) or re.search(r"(\d+)$", path)
        return match.group(1) if match else None

    def _normalize_url(self, url: str | None) -> str | None:
        if not url:
            return None
        absolute = urljoin("https://www.avito.ru", url)
        parts = urlsplit(absolute)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

    def _parse_price(self, value) -> int | None:
        if value is None:
            return None
        digits = re.sub(r"\D", "", str(value))
        return int(digits) if digits else None

    def _text(self, node) -> str | None:
        if not node:
            return None
        text = node.get_text(" ", strip=True)
        return text or None

    def _walk_dicts(self, value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from self._walk_dicts(child)
        elif isinstance(value, list):
            for child in value:
                yield from self._walk_dicts(child)

    def _deduplicate(self, listings: list[ParsedListing]) -> list[ParsedListing]:
        seen = set()
        unique = []
        for listing in listings:
            key = listing.external_id
            if key in seen:
                continue
            seen.add(key)
            unique.append(listing)
        return unique
