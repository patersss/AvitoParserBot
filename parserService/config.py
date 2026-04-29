import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    rabbitmq_url: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    task_events_queue: str = os.getenv("PARSER_TASK_EVENTS_QUEUE", "parser.task_events")
    notification_exchange: str = os.getenv("NOTIFICATION_EXCHANGE", "notification.events")
    listing_found_routing_key: str = os.getenv("LISTING_FOUND_ROUTING_KEY", "listing.found")
    scheduler_tick_seconds: int = int(os.getenv("SCHEDULER_TICK_SECONDS", "30"))
    avito_cookie_header: str = os.getenv("AVITO_COOKIE_HEADER", "")
    avito_cookies_json: str = os.getenv("AVITO_COOKIES_JSON", "")
    avito_user_agent: str = os.getenv(
        "AVITO_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )

    @property
    def avito_cookies(self) -> dict[str, str]:
        if self.avito_cookies_json:
            try:
                raw = json.loads(self.avito_cookies_json)
                if isinstance(raw, list):
                    return {item["name"]: item["value"] for item in raw if "name" in item and "value" in item}
                if isinstance(raw, dict):
                    return {str(key): str(value) for key, value in raw.items()}
            except json.JSONDecodeError:
                pass

        if not self.avito_cookie_header:
            return {}

        cookies = {}
        for part in self.avito_cookie_header.split(";"):
            if "=" not in part:
                continue
            name, value = part.split("=", 1)
            cookies[name.strip()] = value.strip()
        return cookies


settings = Settings()
