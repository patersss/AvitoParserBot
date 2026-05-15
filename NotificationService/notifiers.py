import html
import logging
from email.headerregistry import Address
from email.message import EmailMessage
from typing import Any

import aiohttp
import aiosmtplib

from config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

class EmailNotifier:
    def _is_configured(self) -> bool:
        return bool(settings.smtp_host and settings.smtp_username)

    async def _send(self, to: str, subject: str, html_body: str, text_body: str) -> None:
        if not self._is_configured():
            raise RuntimeError(
                "SMTP is not configured. Set SMTP_HOST, SMTP_USERNAME, and SMTP_PASSWORD."
            )

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = Address(settings.email_from_name, addr_spec=settings.email_from)
        msg["To"] = to
        msg.set_content(text_body, charset="utf-8")
        msg.add_alternative(html_body, subtype="html", charset="utf-8")

        smtp_kwargs: dict[str, Any] = {
            "hostname": settings.smtp_host,
            "port": settings.smtp_port,
            "username": settings.smtp_username,
            "password": settings.smtp_password,
            "timeout": settings.smtp_timeout_seconds,
        }
        if settings.smtp_use_ssl:
            smtp_kwargs["use_tls"] = True
        elif settings.smtp_starttls:
            smtp_kwargs["start_tls"] = True

        await aiosmtplib.send(msg, **smtp_kwargs)

    async def send_listings_batch(self, config: dict, event: dict) -> None:
        email = config.get("email")
        if not email:
            raise ValueError("Email channel config requires 'email' field")

        task_name = event.get("task_name") or "без названия"
        listings = event.get("listings") or []
        if not listings:
            return

        count = len(listings)
        subject = f"Найдено {count} {_plural_ru(count, 'объявление', 'объявления', 'объявлений')}: {task_name}"
        html_body = _listings_batch_html(task_name, listings)
        text_body = f"Найдено {count} новых объявлений по задаче «{task_name}»\n\n"
        for listing in listings:
            title = listing.get("title") or "Новое объявление"
            price = format_price(listing.get("price"))
            url = listing.get("url") or ""
            text_body += f"— {title}\n  Цена: {price}\n  {url}\n\n"

        await self._send(email, subject, html_body, text_body)
        logger.info("Email batch notification sent to %s (%d listings)", email, count)

    async def send_listing(self, config: dict, event: dict) -> None:
        email = config.get("email")
        if not email:
            raise ValueError("Email channel config requires 'email' field")

        listing = event.get("listing") or {}
        task_name = event.get("task_name") or "без названия"
        title = listing.get("title") or "Новое объявление"
        price = format_price(listing.get("price"))
        url = listing.get("url") or ""
        platform = listing.get("platform") or event.get("platform") or "unknown"

        subject = f"Новое объявление: {title}"
        html_body = _listing_html(title, price, platform, task_name, url)
        text_body = (
            f"Найдено новое объявление\n\n"
            f"{title}\nЦена: {price}\nПлатформа: {platform}\nЗадача: {task_name}\n{url}"
        )

        await self._send(email, subject, html_body, text_body)
        logger.info("Email listing notification sent to %s", email)

    async def send_verification_code(self, email: str, code: str, expires_in_minutes: int = 10) -> None:
        subject = "Код подтверждения"
        html_body = _verification_html(code, expires_in_minutes)
        text_body = (
            f"Ваш код подтверждения: {code}\n"
            f"Код действителен {expires_in_minutes} минут.\n\n"
            "Если вы не запрашивали код — просто проигнорируйте это письмо."
        )
        await self._send(email, subject, html_body, text_body)
        logger.info("Verification code email sent to %s", email)

    async def send_password_reset(self, email: str, reset_link: str) -> None:
        subject = "Сброс пароля"
        html_body = _password_reset_html(reset_link)
        text_body = (
            f"Для сброса пароля перейдите по ссылке:\n{reset_link}\n\n"
            "Ссылка действительна в течение ограниченного времени.\n"
            "Если вы не запрашивали сброс пароля — просто проигнорируйте это письмо."
        )
        await self._send(email, subject, html_body, text_body)
        logger.info("Password reset email sent to %s", email)


# ---------------------------------------------------------------------------
# HTML templates
# ---------------------------------------------------------------------------

_BASE_STYLE = """
  body { margin: 0; padding: 0; background: #f4f4f5; font-family: Arial, sans-serif; }
  .wrap { max-width: 560px; margin: 32px auto; background: #ffffff;
          border-radius: 8px; overflow: hidden; }
  .header { background: #2563eb; padding: 24px 32px; }
  .header h1 { margin: 0; color: #ffffff; font-size: 18px; font-weight: 700; }
  .body { padding: 28px 32px; color: #374151; font-size: 15px; line-height: 1.6; }
  .code { display: inline-block; background: #eff6ff; color: #1d4ed8;
          font-size: 32px; font-weight: 700; letter-spacing: 8px;
          padding: 16px 28px; border-radius: 6px; margin: 20px 0; }
  .btn { display: inline-block; background: #2563eb; color: #ffffff;
         text-decoration: none; padding: 12px 28px; border-radius: 6px;
         font-size: 15px; font-weight: 600; margin: 20px 0; }
  .field { margin: 6px 0; }
  .label { color: #6b7280; font-size: 13px; }
  .value { font-weight: 600; font-size: 15px; }
  .price { color: #16a34a; }
  .link-block { word-break: break-all; margin: 12px 0; }
  .link-block a:not(.btn) { color: #2563eb; }
  .footer { padding: 16px 32px; background: #f9fafb; color: #9ca3af;
             font-size: 12px; text-align: center; }
"""


def _html_doc(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html><html><head>"
        f'<meta charset="utf-8"><title>{html.escape(title)}</title>'
        f"<style>{_BASE_STYLE}</style></head><body>"
        '<div class="wrap">'
        f'<div class="header"><h1>{html.escape(title)}</h1></div>'
        f'<div class="body">{body}</div>'
        '<div class="footer">Parser Monitor &mdash; автоматическое уведомление</div>'
        "</div></body></html>"
    )


def _listing_html(title: str, price: str, platform: str, task_name: str, url: str) -> str:
    body = (
        "<p>Найдено новое объявление по вашей задаче мониторинга.</p>"
        f'<div class="field"><span class="label">Название</span><br>'
        f'<span class="value">{html.escape(title)}</span></div>'
        f'<div class="field"><span class="label">Цена</span><br>'
        f'<span class="value price">{html.escape(price)}</span></div>'
        f'<div class="field"><span class="label">Платформа</span><br>'
        f'<span class="value">{html.escape(platform)}</span></div>'
        f'<div class="field"><span class="label">Задача</span><br>'
        f'<span class="value">{html.escape(task_name)}</span></div>'
    )
    if url:
        body += (
            f'<div class="link-block">'
            f'<a class="btn" href="{html.escape(url)}">Просмотреть</a>'
            f"</div>"
        )
    return _html_doc("Новое объявление", body)


def _listings_batch_html(task_name: str, listings: list[dict]) -> str:
    count = len(listings)
    body = f"<p>Найдено <strong>{count}</strong> новых объявлений по задаче <strong>{html.escape(task_name)}</strong>.</p>"
    for listing in listings:
        title = listing.get("title") or "Новое объявление"
        price = format_price(listing.get("price"))
        url = listing.get("url") or ""
        body += (
            '<div style="border:1px solid #e5e7eb;border-radius:6px;padding:14px 16px;margin:12px 0;">'
            f'<div class="field"><span class="value">{html.escape(title)}</span></div>'
            f'<div class="field"><span class="label">Цена: </span>'
            f'<span class="value price">{html.escape(price)}</span></div>'
        )
        if url:
            body += f'<div class="link-block"><a class="btn" href="{html.escape(url, quote=True)}">Просмотреть</a></div>'
        body += "</div>"
    return _html_doc(f"Найдено {count} объявлений", body)


def _verification_html(code: str, expires_in_minutes: int) -> str:
    body = (
        "<p>Ваш код подтверждения:</p>"
        f'<div class="code">{html.escape(code)}</div>'
        f"<p>Код действителен <strong>{expires_in_minutes} минут</strong>.</p>"
        "<p>Если вы не запрашивали код — просто проигнорируйте это письмо.</p>"
    )
    return _html_doc("Код подтверждения", body)


def _password_reset_html(reset_link: str) -> str:
    body = (
        "<p>Получен запрос на сброс пароля для вашего аккаунта.</p>"
        f'<div><a class="btn" href="{html.escape(reset_link)}">Сбросить пароль</a></div>'
        "<p>Если кнопка не работает, скопируйте ссылку в браузер:</p>"
        f'<div class="link-block"><a href="{html.escape(reset_link)}">'
        f"{html.escape(reset_link)}</a></div>"
        "<p>Если вы не запрашивали сброс пароля — просто проигнорируйте это письмо.</p>"
    )
    return _html_doc("Сброс пароля", body)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

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


def _plural_ru(n: int, form1: str, form2: str, form5: str) -> str:
    """Return Russian plural form: 1 объявление, 2 объявления, 5 объявлений."""
    n = abs(n) % 100
    if 11 <= n <= 19:
        return form5
    n = n % 10
    if n == 1:
        return form1
    if 2 <= n <= 4:
        return form2
    return form5


def format_price(value) -> str:
    if value is None:
        return "не указана"
    try:
        return f"{int(value):,}".replace(",", " ") + " руб."
    except (TypeError, ValueError):
        return str(value)
