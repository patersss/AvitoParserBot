import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus

import aio_pika
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import BotCommand, BotCommandScopeDefault, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    api_core_base_url: str = os.getenv("API_CORE_BASE_URL", "http://localhost:8000").rstrip("/")
    service_api_token: str = os.getenv("SERVICE_API_TOKEN", "dev-service-token")
    site_login_url: str = os.getenv("SITE_LOGIN_URL", "http://localhost:3000/login?token={token}")
    rabbitmq_url: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    notification_exchange: str = os.getenv("NOTIFICATION_EXCHANGE", "notification.events")
    notification_channel_routing_key: str = os.getenv(
        "NOTIFICATION_CHANNEL_ROUTING_KEY",
        "notification.channel.upserted",
    )
    request_timeout_seconds: int = int(os.getenv("BOT_HTTP_TIMEOUT_SECONDS", "15"))
    min_interval_minutes: int = int(os.getenv("MIN_TASK_INTERVAL_MINUTES", "10"))
    max_task_days: int = int(os.getenv("MAX_TASK_DAYS", "365"))


settings = Settings()
if not settings.telegram_token:
    raise RuntimeError("TELEGRAM_TOKEN is required")

bot = Bot(token=settings.telegram_token)
dp = Dispatcher()
user_states: dict[int, dict[str, Any]] = {}


class ApiCoreError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"ApiCoreService returned {status}: {message}")


class ApiCoreClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout_seconds)
        self.session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self.session:
            await self.session.close()

    async def upsert_telegram_user(self, telegram_user: types.User, chat_id: int) -> dict:
        payload = {
            "telegram_user_id": telegram_user.id,
            "chat_id": chat_id,
            "username": telegram_user.username or telegram_user.full_name,
            "avatar_url": None,
        }
        return await self._request(
            "POST",
            "/telegram/users/upsert",
            json_data=payload,
            service_auth=True,
        )

    async def create_site_login_token(self, telegram_user_id: int, chat_id: int) -> dict:
        return await self._request(
            "POST",
            "/telegram/login-token",
            json_data={"telegram_user_id": telegram_user_id, "chat_id": chat_id},
            service_auth=True,
        )

    async def create_user_access_token(self, telegram_user: types.User, chat_id: int) -> tuple[str, dict]:
        await self.upsert_telegram_user(telegram_user, chat_id)
        login_token = await self.create_site_login_token(telegram_user.id, chat_id)
        auth = await self._request("POST", "/auth/telegram-token", json_data={"token": login_token["token"]})
        return auth["access_token"], auth["user"]

    async def list_tasks(self, access_token: str, *, include_inactive: bool = True) -> list[dict]:
        return await self._request(
            "GET",
            "/tasks",
            access_token=access_token,
            params={"include_inactive": str(include_inactive).lower(), "limit": "100"},
        )

    async def create_task(self, access_token: str, payload: dict) -> dict:
        return await self._request("POST", "/tasks", json_data=payload, access_token=access_token)

    async def update_task(self, access_token: str, task_id: str, payload: dict) -> dict:
        return await self._request("PATCH", f"/tasks/{task_id}", json_data=payload, access_token=access_token)

    async def delete_task(self, access_token: str, task_id: str) -> dict:
        return await self._request("DELETE", f"/tasks/{task_id}", access_token=access_token)

    async def refresh_task(self, access_token: str, task_id: str) -> dict:
        return await self._request("POST", f"/tasks/{task_id}/refresh", access_token=access_token)

    async def list_task_listings(self, access_token: str, task_id: str, *, limit: int = 10) -> list[dict]:
        return await self._request(
            "GET",
            f"/tasks/{task_id}/listings",
            access_token=access_token,
            params={"limit": str(limit)},
        )

    async def list_listings(self, access_token: str, *, limit: int = 10) -> list[dict]:
        return await self._request("GET", "/listings", access_token=access_token, params={"limit": str(limit)})

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: dict | None = None,
        params: dict | None = None,
        service_auth: bool = False,
        access_token: str | None = None,
    ):
        if not self.session:
            await self.connect()

        headers = {"Accept": "application/json"}
        if service_auth:
            headers["X-Service-Token"] = self.settings.service_api_token
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        url = f"{self.settings.api_core_base_url}{path}"
        assert self.session is not None
        async with self.session.request(method, url, json=json_data, params=params, headers=headers) as response:
            text = await response.text()
            data = {}
            if text:
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    data = {"detail": text}
            if response.status >= 400:
                detail = data.get("detail") if isinstance(data, dict) else text
                raise ApiCoreError(response.status, str(detail))
            return data


class NotificationEventPublisher:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.connection: aio_pika.RobustConnection | None = None
        self.channel: aio_pika.RobustChannel | None = None
        self.exchange: aio_pika.RobustExchange | None = None

    async def connect(self) -> None:
        self.connection = await aio_pika.connect_robust(self.settings.rabbitmq_url)
        self.channel = await self.connection.channel()
        self.exchange = await self.channel.declare_exchange(
            self.settings.notification_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        logger.info("Connected to RabbitMQ notification exchange")

    async def close(self) -> None:
        if self.connection:
            await self.connection.close()

    async def publish_telegram_channel(self, user: dict, telegram_user: types.User, chat_id: int) -> None:
        if not self.exchange:
            await self.connect()

        payload = {
            "event_type": "notification_channel.upserted",
            "source_service": "BotService",
            "user_id": user["id"],
            "channel": {
                "type": "telegram",
                "config": {
                    "telegram_user_id": telegram_user.id,
                    "chat_id": chat_id,
                    "username": telegram_user.username,
                },
                "is_active": True,
            },
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        message = aio_pika.Message(
            body=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        assert self.exchange is not None
        await self.exchange.publish(message, routing_key=self.settings.notification_channel_routing_key)


api_core = ApiCoreClient(settings)
notifications = NotificationEventPublisher(settings)


def platform_keyboard(prefix: str = "add_platform") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Avito", callback_data=f"{prefix}:avito"),
                InlineKeyboardButton(text="Cian", callback_data=f"{prefix}:cian"),
                InlineKeyboardButton(text="Youla", callback_data=f"{prefix}:youla"),
            ]
        ]
    )


def task_keyboard(task: dict) -> InlineKeyboardMarkup:
    task_id = task["id"]
    active = bool(task.get("is_active"))
    toggle_action = "pause" if active else "resume"
    toggle_text = "Пауза" if active else "Возобновить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Объявления", callback_data=f"task_listings:{task_id}"),
                InlineKeyboardButton(text="Обновить", callback_data=f"task_refresh:{task_id}"),
            ],
            [
                InlineKeyboardButton(text="Название", callback_data=f"task_edit_name:{task_id}"),
                InlineKeyboardButton(text="URL", callback_data=f"task_edit_url:{task_id}"),
                InlineKeyboardButton(text="Интервал", callback_data=f"task_edit_interval:{task_id}"),
            ],
            [
                InlineKeyboardButton(text=toggle_text, callback_data=f"task_{toggle_action}:{task_id}"),
                InlineKeyboardButton(text="Удалить", callback_data=f"task_delete:{task_id}"),
            ],
        ]
    )


def tasks_picker_keyboard(tasks: list[dict], action: str) -> InlineKeyboardMarkup:
    rows = []
    for task in tasks:
        name = task.get("name") or task["url"][:32]
        rows.append([InlineKeyboardButton(text=name[:60], callback_data=f"{action}:{task['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_task(task: dict) -> str:
    status = "активна" if task.get("is_active") else "на паузе"
    end_date = format_datetime(task.get("end_date")) if task.get("end_date") else "без даты окончания"
    name = task.get("name") or "без названия"
    return (
        f"Задача: {name}\n"
        f"Платформа: {task['platform']}\n"
        f"Статус: {status}\n"
        f"Интервал: {task['interval_minutes']} мин.\n"
        f"До: {end_date}\n"
        f"URL: {task['url']}\n"
        f"ID: {task['id']}"
    )


def format_listing(listing: dict) -> str:
    price = f"{listing['price']} руб." if listing.get("price") is not None else "цена не указана"
    created_at = format_datetime(listing.get("created_at"))
    return (
        f"{listing.get('title') or 'Без названия'}\n"
        f"{price}\n"
        f"{listing['url']}\n"
        f"Найдено: {created_at}"
    )


def format_datetime(value: str | None) -> str:
    if not value:
        return "не указано"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.astimezone().strftime("%d.%m.%Y %H:%M")


def build_site_login_link(token: str) -> str:
    encoded = quote_plus(token)
    if "{token}" in settings.site_login_url:
        return settings.site_login_url.format(token=encoded)
    separator = "&" if "?" in settings.site_login_url else "?"
    return f"{settings.site_login_url}{separator}token={encoded}"


def validate_platform_url(platform: str, url: str) -> bool:
    platform_domains = {"avito": "avito.ru", "cian": "cian.ru", "youla": "youla.ru"}
    return platform_domains[platform] in url.lower()


async def get_access_token_for_message(message: types.Message) -> str:
    token, _user = await api_core.create_user_access_token(message.from_user, message.chat.id)
    return token


async def get_access_token_for_callback(callback: types.CallbackQuery) -> str:
    assert callback.message is not None
    token, _user = await api_core.create_user_access_token(callback.from_user, callback.message.chat.id)
    return token


async def send_api_error(target: types.Message, error: ApiCoreError) -> None:
    if error.status == 403:
        await target.answer("Доступ запрещён. Возможно, аккаунт заблокирован.")
    elif error.status == 404:
        await target.answer("Не нашёл нужные данные. Попробуйте /start и повторите действие.")
    else:
        await target.answer(f"ApiCoreService вернул ошибку: {error.message}")


@dp.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    try:
        result = await api_core.upsert_telegram_user(message.from_user, message.chat.id)
        await notifications.publish_telegram_channel(result["user"], message.from_user, message.chat.id)
    except Exception:
        logger.exception("Failed to initialize Telegram user")
        await message.answer("Не удалось зарегистрировать Telegram-аккаунт. Попробуйте позже.")
        return

    await message.answer(
        "Привет! Я помогу отслеживать новые объявления.\n\n"
        "Что можно сделать:\n"
        "/add - создать задачу парсинга\n"
        "/tasks - посмотреть и управлять задачами\n"
        "/listings - последние найденные объявления\n"
        "/login - получить одноразовую ссылку для входа на сайт\n"
        "/help - подробная справка"
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    await message.answer(
        "Команды:\n"
        "/start - создать или обновить Telegram-профиль\n"
        "/add - добавить задачу\n"
        "/tasks или /list - список задач и кнопки управления\n"
        "/listings - выбрать задачу и посмотреть найденные объявления\n"
        "/remove - выбрать задачу для удаления\n"
        "/login - одноразовая ссылка для входа на сайт\n"
        "/cancel - отменить текущий ввод\n\n"
        "Поддерживаемые платформы: Avito, Cian, Youla.\n"
        "Минимальный интервал проверки: "
        f"{settings.min_interval_minutes} минут."
    )


@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message) -> None:
    user_states.pop(message.chat.id, None)
    await message.answer("Ок, текущий ввод отменён.")


@dp.message(Command("login"))
async def cmd_login(message: types.Message) -> None:
    try:
        await api_core.upsert_telegram_user(message.from_user, message.chat.id)
        token_payload = await api_core.create_site_login_token(message.from_user.id, message.chat.id)
    except ApiCoreError as error:
        await send_api_error(message, error)
        return
    except Exception:
        logger.exception("Failed to create site login token")
        await message.answer("Не удалось создать ссылку для входа. Попробуйте позже.")
        return

    link = build_site_login_link(token_payload["token"])
    expires_at = format_datetime(token_payload.get("expires_at"))
    await message.answer(
        "Одноразовая ссылка для входа на сайт:\n"
        f"{link}\n\n"
        f"Действует до: {expires_at}\n"
        "Если ссылка уже использована, запросите новую командой /login."
    )


@dp.message(Command("add"))
async def cmd_add(message: types.Message) -> None:
    user_states[message.chat.id] = {"flow": "add", "step": "name"}
    await message.answer("Введите название задачи.")


@dp.message(Command("tasks", "list"))
async def cmd_tasks(message: types.Message) -> None:
    await show_tasks(message)


@dp.message(Command("remove"))
async def cmd_remove(message: types.Message) -> None:
    try:
        token = await get_access_token_for_message(message)
        tasks = await api_core.list_tasks(token, include_inactive=True)
    except ApiCoreError as error:
        await send_api_error(message, error)
        return

    if not tasks:
        await message.answer("У вас пока нет задач для удаления.")
        return

    await message.answer("Выберите задачу для удаления:", reply_markup=tasks_picker_keyboard(tasks, "task_delete"))


@dp.message(Command("listings"))
async def cmd_listings(message: types.Message) -> None:
    try:
        token = await get_access_token_for_message(message)
        tasks = await api_core.list_tasks(token, include_inactive=True)
    except ApiCoreError as error:
        await send_api_error(message, error)
        return

    if not tasks:
        listings = await api_core.list_listings(token, limit=10)
        if not listings:
            await message.answer("Пока нет найденных объявлений.")
            return
        await message.answer(format_listings(listings))
        return

    await message.answer("Выберите задачу:", reply_markup=tasks_picker_keyboard(tasks, "task_listings"))


async def show_tasks(message: types.Message) -> None:
    try:
        token = await get_access_token_for_message(message)
        tasks = await api_core.list_tasks(token, include_inactive=True)
    except ApiCoreError as error:
        await send_api_error(message, error)
        return

    if not tasks:
        await message.answer("У вас пока нет задач. Создайте первую командой /add.")
        return

    await message.answer("Ваши задачи:")
    for task in tasks:
        await message.answer(format_task(task), reply_markup=task_keyboard(task))


@dp.callback_query(F.data.startswith("add_platform:"))
async def process_add_platform(callback: types.CallbackQuery) -> None:
    platform = callback.data.split(":", 1)[1]
    state = user_states.setdefault(callback.message.chat.id, {})
    if state.get("flow") != "add":
        await callback.answer("Сценарий добавления уже не активен.", show_alert=True)
        return

    state["platform"] = platform
    state["step"] = "url"
    await callback.message.answer(f"Платформа: {platform}. Теперь отправьте ссылку на поиск.")
    await callback.answer()


@dp.callback_query(F.data.startswith("task_listings:"))
async def process_task_listings(callback: types.CallbackQuery) -> None:
    task_id = callback.data.split(":", 1)[1]
    try:
        token = await get_access_token_for_callback(callback)
        listings = await api_core.list_task_listings(token, task_id, limit=10)
    except ApiCoreError as error:
        await callback.message.answer(f"Не удалось получить объявления: {error.message}")
        await callback.answer()
        return

    if not listings:
        await callback.message.answer("Для этой задачи пока нет найденных объявлений.")
    else:
        await callback.message.answer(format_listings(listings))
    await callback.answer()


@dp.callback_query(F.data.startswith("task_refresh:"))
async def process_task_refresh(callback: types.CallbackQuery) -> None:
    task_id = callback.data.split(":", 1)[1]
    try:
        token = await get_access_token_for_callback(callback)
        await api_core.refresh_task(token, task_id)
    except ApiCoreError as error:
        await callback.message.answer(f"Не удалось запросить обновление: {error.message}")
    else:
        await callback.message.answer("Запросил обновление задачи. ParserService подхватит её на ближайшем цикле.")
    await callback.answer()


@dp.callback_query(F.data.startswith("task_edit_name:"))
async def process_task_edit_name(callback: types.CallbackQuery) -> None:
    await start_edit_flow(callback, "name", "Введите новое название задачи.")


@dp.callback_query(F.data.startswith("task_edit_url:"))
async def process_task_edit_url(callback: types.CallbackQuery) -> None:
    await start_edit_flow(callback, "url", "Отправьте новую ссылку. Она должна соответствовать платформе задачи.")


@dp.callback_query(F.data.startswith("task_edit_interval:"))
async def process_task_edit_interval(callback: types.CallbackQuery) -> None:
    await start_edit_flow(
        callback,
        "interval",
        f"Введите новый интервал в минутах, минимум {settings.min_interval_minutes}.",
    )


async def start_edit_flow(callback: types.CallbackQuery, field: str, prompt: str) -> None:
    task_id = callback.data.split(":", 1)[1]
    user_states[callback.message.chat.id] = {"flow": "edit", "field": field, "task_id": task_id}
    await callback.message.answer(prompt)
    await callback.answer()


@dp.callback_query(F.data.startswith("task_pause:"))
async def process_task_pause(callback: types.CallbackQuery) -> None:
    await update_task_active(callback, is_active=False)


@dp.callback_query(F.data.startswith("task_resume:"))
async def process_task_resume(callback: types.CallbackQuery) -> None:
    await update_task_active(callback, is_active=True)


async def update_task_active(callback: types.CallbackQuery, *, is_active: bool) -> None:
    task_id = callback.data.split(":", 1)[1]
    try:
        token = await get_access_token_for_callback(callback)
        task = await api_core.update_task(token, task_id, {"is_active": is_active})
    except ApiCoreError as error:
        await callback.message.answer(f"Не удалось обновить задачу: {error.message}")
    else:
        await callback.message.answer(format_task(task), reply_markup=task_keyboard(task))
    await callback.answer()


@dp.callback_query(F.data.startswith("task_delete:"))
async def process_task_delete(callback: types.CallbackQuery) -> None:
    task_id = callback.data.split(":", 1)[1]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, удалить", callback_data=f"task_delete_confirm:{task_id}"),
                InlineKeyboardButton(text="Отмена", callback_data="noop"),
            ]
        ]
    )
    await callback.message.answer("Удалить задачу? Это остановит парсинг, но история объявлений сохранится.", reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(F.data.startswith("task_delete_confirm:"))
async def process_task_delete_confirm(callback: types.CallbackQuery) -> None:
    task_id = callback.data.split(":", 1)[1]
    try:
        token = await get_access_token_for_callback(callback)
        await api_core.delete_task(token, task_id)
    except ApiCoreError as error:
        await callback.message.answer(f"Не удалось удалить задачу: {error.message}")
    else:
        await callback.message.answer("Задача удалена.")
    await callback.answer()


@dp.callback_query(F.data == "noop")
async def process_noop(callback: types.CallbackQuery) -> None:
    await callback.answer("Отменено")


@dp.message(lambda message: message.chat.id in user_states)
async def process_state_message(message: types.Message) -> None:
    state = user_states.get(message.chat.id)
    if not state:
        return

    if state.get("flow") == "add":
        await process_add_state(message, state)
    elif state.get("flow") == "edit":
        await process_edit_state(message, state)


async def process_add_state(message: types.Message, state: dict[str, Any]) -> None:
    text = (message.text or "").strip()
    if state.get("step") == "name":
        if len(text) < 3 or len(text) > 150:
            await message.answer("Название должно быть от 3 до 150 символов.")
            return
        state["name"] = text
        state["step"] = "platform"
        await message.answer("Выберите платформу:", reply_markup=platform_keyboard())
        return

    if state.get("step") == "url":
        platform = state["platform"]
        if not validate_platform_url(platform, text):
            await message.answer("Ссылка не похожа на выбранную платформу. Отправьте корректную ссылку.")
            return
        state["url"] = text
        state["step"] = "days"
        await message.answer(f"Сколько дней отслеживать? Введите число от 1 до {settings.max_task_days}.")
        return

    if state.get("step") == "days":
        try:
            days = int(text)
            if days < 1 or days > settings.max_task_days:
                raise ValueError
        except ValueError:
            await message.answer(f"Введите число дней от 1 до {settings.max_task_days}.")
            return
        state["days"] = days
        state["step"] = "interval"
        await message.answer(f"Введите интервал проверки в минутах, минимум {settings.min_interval_minutes}.")
        return

    if state.get("step") == "interval":
        try:
            interval = int(text)
            if interval < settings.min_interval_minutes:
                raise ValueError
        except ValueError:
            await message.answer(f"Введите число не меньше {settings.min_interval_minutes}.")
            return

        end_date = datetime.now(timezone.utc) + timedelta(days=state["days"])
        payload = {
            "name": state["name"],
            "platform": state["platform"],
            "url": state["url"],
            "interval_minutes": interval,
            "end_date": end_date.isoformat(),
            "is_active": True,
        }
        try:
            token = await get_access_token_for_message(message)
            task = await api_core.create_task(token, payload)
        except ApiCoreError as error:
            await send_api_error(message, error)
            return
        finally:
            user_states.pop(message.chat.id, None)

        await message.answer("Задача создана:\n\n" + format_task(task), reply_markup=task_keyboard(task))


async def process_edit_state(message: types.Message, state: dict[str, Any]) -> None:
    text = (message.text or "").strip()
    task_id = state["task_id"]
    field = state["field"]

    payload: dict[str, Any]
    if field == "name":
        if len(text) < 3 or len(text) > 150:
            await message.answer("Название должно быть от 3 до 150 символов.")
            return
        payload = {"name": text}
    elif field == "interval":
        try:
            interval = int(text)
            if interval < settings.min_interval_minutes:
                raise ValueError
        except ValueError:
            await message.answer(f"Введите число не меньше {settings.min_interval_minutes}.")
            return
        payload = {"interval_minutes": interval}
    elif field == "url":
        if not text.startswith("http"):
            await message.answer("Отправьте корректную ссылку.")
            return
        payload = {"url": text}
    else:
        user_states.pop(message.chat.id, None)
        await message.answer("Неизвестное поле редактирования.")
        return

    try:
        token = await get_access_token_for_message(message)
        task = await api_core.update_task(token, task_id, payload)
    except ApiCoreError as error:
        await send_api_error(message, error)
        return
    finally:
        user_states.pop(message.chat.id, None)

    await message.answer("Задача обновлена:\n\n" + format_task(task), reply_markup=task_keyboard(task))


def format_listings(listings: list[dict]) -> str:
    chunks = ["Последние найденные объявления:"]
    for index, listing in enumerate(listings, start=1):
        chunks.append(f"{index}. {format_listing(listing)}")
    return "\n\n".join(chunks)


async def set_commands(current_bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Начать работу и включить Telegram-уведомления"),
        BotCommand(command="add", description="Добавить задачу парсинга"),
        BotCommand(command="tasks", description="Показать задачи"),
        BotCommand(command="listings", description="Показать найденные объявления"),
        BotCommand(command="login", description="Получить ссылку для входа на сайт"),
        BotCommand(command="help", description="Справка"),
        BotCommand(command="cancel", description="Отменить текущий ввод"),
    ]
    await current_bot.set_my_commands(commands, scope=BotCommandScopeDefault())


async def main() -> None:
    await api_core.connect()
    try:
        try:
            await notifications.connect()
        except Exception:
            logger.exception("RabbitMQ is unavailable. Telegram channel events will retry on demand.")
        await set_commands(bot)
        await dp.start_polling(bot)
    finally:
        await api_core.close()
        await notifications.close()


if __name__ == "__main__":
    asyncio.run(main())
