"""
Minimal VK bot for linking VK accounts to Parser Monitor notifications.

The bot uses VK Long Poll API to receive messages. When a user sends any
message the bot treats it as a linking token, calls
POST /notification-channels/vk/link on ApiCoreService, and replies with a
confirmation or an error description.

Required env vars:
  VK_GROUP_TOKEN      - VK community token with `messages` permission
  VK_GROUP_ID         - numeric VK group (community) ID
  SERVICE_API_TOKEN   - X-Service-Token for ApiCoreService calls
  API_CORE_BASE_URL   - e.g. http://api-core:8000  (default localhost:8000)

Optional:
  VK_API_VERSION      - VK API version (default 5.199)
  BOT_HTTP_TIMEOUT    - seconds per HTTP request (default 10)
"""
import asyncio
import logging
import os

import aiohttp
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("vk_bot")

VK_GROUP_TOKEN: str = os.getenv("VK_GROUP_TOKEN", "")
VK_GROUP_ID: str = os.getenv("VK_GROUP_ID", "")
VK_API_VERSION: str = os.getenv("VK_API_VERSION", "5.199")
API_CORE_BASE_URL: str = os.getenv("API_CORE_BASE_URL", "http://localhost:8000").rstrip("/")
SERVICE_API_TOKEN: str = os.getenv("SERVICE_API_TOKEN", "dev-service-token")
HTTP_TIMEOUT: int = int(os.getenv("BOT_HTTP_TIMEOUT", "10"))

VK_API = "https://api.vk.com/method"


async def vk_api(session: aiohttp.ClientSession, method: str, **params) -> dict:
    params.update({"access_token": VK_GROUP_TOKEN, "v": VK_API_VERSION})
    async with session.post(f"{VK_API}/{method}", data=params) as resp:
        data = await resp.json()
    if "error" in data:
        err = data["error"]
        raise RuntimeError(f"VK {method} error {err.get('error_code')}: {err.get('error_msg')}")
    return data.get("response", data)


async def send_message(session: aiohttp.ClientSession, peer_id: int, text: str) -> None:
    import secrets
    await vk_api(session, "messages.send", peer_id=peer_id, message=text, random_id=secrets.randbelow(2**31))


async def link_vk_channel(session: aiohttp.ClientSession, token: str, vk_user_id: int) -> str:
    url = f"{API_CORE_BASE_URL}/notification-channels/vk/link"
    headers = {"X-Service-Token": SERVICE_API_TOKEN, "Content-Type": "application/json"}
    import json as _json
    async with session.post(url, data=_json.dumps({"token": token, "vk_user_id": vk_user_id}), headers=headers) as resp:
        body = await resp.json()
        if resp.status == 200:
            return "ok"
        detail = body.get("detail", "Неизвестная ошибка")
        return str(detail)


async def process_message(session: aiohttp.ClientSession, event: dict) -> None:
    obj = event.get("object", {})
    msg = obj.get("message", obj)
    peer_id: int = msg.get("peer_id") or msg.get("from_id", 0)
    user_id: int = msg.get("from_id", peer_id)
    text: str = (msg.get("text") or "").strip()

    if not text or peer_id < 0:
        return

    result = await link_vk_channel(session, text, user_id)
    if result == "ok":
        await send_message(session, peer_id, "Аккаунт ВКонтакте успешно привязан. Теперь вы будете получать уведомления о новых объявлениях.")
    elif "already used" in result.lower():
        await send_message(session, peer_id, "Код уже был использован. Сгенерируйте новый на сайте.")
    elif "expired" in result.lower():
        await send_message(session, peer_id, "Код истёк. Сгенерируйте новый на сайте.")
    elif "not found" in result.lower():
        await send_message(session, peer_id, "Код не найден. Убедитесь, что скопировали его полностью.")
    else:
        await send_message(session, peer_id, f"Не удалось привязать аккаунт: {result}")


async def run() -> None:
    if not VK_GROUP_TOKEN:
        raise RuntimeError("VK_GROUP_TOKEN is required")
    if not VK_GROUP_ID:
        raise RuntimeError("VK_GROUP_ID is required")

    api_timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
    lp_timeout = aiohttp.ClientTimeout(total=35)  # wait=25 + network margin
    async with aiohttp.ClientSession(timeout=api_timeout) as session:
        lp = await vk_api(session, "groups.getLongPollServer", group_id=VK_GROUP_ID)
        server: str = lp["server"]
        key: str = lp["key"]
        ts: str = lp["ts"]
        logger.info("VK Long Poll started (group_id=%s)", VK_GROUP_ID)

        while True:
            try:
                url = f"{server}?act=a_check&key={key}&ts={ts}&wait=25"
                async with session.get(url, timeout=lp_timeout) as resp:
                    data = await resp.json()
            except Exception:
                logger.exception("Long Poll request failed, retrying in 5s")
                await asyncio.sleep(5)
                continue

            if "failed" in data:
                code = data["failed"]
                if code == 1:
                    ts = data["ts"]
                elif code in (2, 3):
                    lp = await vk_api(session, "groups.getLongPollServer", group_id=VK_GROUP_ID)
                    key = lp["key"]
                    ts = lp["ts"]
                    if code == 3:
                        server = lp["server"]
                continue

            ts = data.get("ts", ts)
            for event in data.get("updates", []):
                if event.get("type") == "message_new":
                    try:
                        await process_message(session, event)
                    except Exception:
                        logger.exception("Failed to process message_new event")


if __name__ == "__main__":
    asyncio.run(run())
