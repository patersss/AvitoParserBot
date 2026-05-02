import html
import logging
from typing import Any

import aiohttp

from config import settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None

    async def close(self):
        if self.session:
            await self.session.close()

    async def send_listing(self, config: dict, event: dict):
        if not settings.telegram_token:
            raise RuntimeError("TELEGRAM_TOKEN is required for Telegram notifications")

        chat_id = config.get("chat_id")
        if not chat_id:
            raise ValueError("Telegram channel config requires chat_id")

        if not self.session:
            self.session = aiohttp.ClientSession()

        text = format_listing_message(event)
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": False,
        }
        if settings.telegram_parse_mode:
            payload["parse_mode"] = settings.telegram_parse_mode

        url = f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage"
        async with self.session.post(url, json=payload) as response:
            if response.status >= 400:
                body = await response.text()
                raise RuntimeError(f"Telegram sendMessage failed with {response.status}: {body}")


class EmailNotifier:
    async def send_listing(self, config: dict, event: dict):
        email = config.get("email")
        logger.info("Email notification stub: would send listing to %s: %s", email, event.get("listing", {}).get("url"))


def format_listing_message(event: dict) -> str:
    listing = event.get("listing") or {}
    task_name = event.get("task_name") or "без названия"
    platform = listing.get("platform") or event.get("platform") or "unknown"
    title = listing.get("title") or "Новое объявление"
    price = format_price(listing.get("price"))
    url = listing.get("url") or ""

    if settings.telegram_parse_mode and settings.telegram_parse_mode.upper() == "HTML":
        return (
            "Найдено новое объявление\n\n"
            f"<b>{html.escape(str(title))}</b>\n"
            f"Цена: {html.escape(price)}\n"
            f"Платформа: {html.escape(str(platform))}\n"
            f"Задача: {html.escape(str(task_name))}\n"
            f"{html.escape(str(url))}"
        )

    return (
        "Найдено новое объявление\n\n"
        f"{title}\n"
        f"Цена: {price}\n"
        f"Платформа: {platform}\n"
        f"Задача: {task_name}\n"
        f"{url}"
    )


def format_price(value) -> str:
    if value is None:
        return "не указана"
    try:
        return f"{int(value):,}".replace(",", " ") + " руб."
    except (TypeError, ValueError):
        return str(value)
