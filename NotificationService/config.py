import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    db_user: str = os.getenv("DB_USER", "postgres")
    db_password: str = os.getenv("DB_PASSWORD", "postgres")
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: str = os.getenv("DB_PORT", "5432")
    db_name: str = os.getenv("DB_NAME", "notification_db")
    db_echo: bool = os.getenv("DB_ECHO", "false").lower() == "true"

    rabbitmq_url: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    notification_exchange: str = os.getenv("NOTIFICATION_EXCHANGE", "notification.events")
    notification_events_queue: str = os.getenv("NOTIFICATION_EVENTS_QUEUE", "notification.events")
    listing_found_routing_key: str = os.getenv("LISTING_FOUND_ROUTING_KEY", "listing.found")
    channel_upserted_routing_key: str = os.getenv("NOTIFICATION_CHANNEL_ROUTING_KEY", "notification.channel.upserted")
    channel_deleted_routing_key: str = os.getenv("NOTIFICATION_CHANNEL_DELETED_ROUTING_KEY", "notification.channel.deleted")

    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    telegram_parse_mode: str | None = os.getenv("TELEGRAM_PARSE_MODE") or None

    # VK Bot
    vk_group_token: str = os.getenv("VK_GROUP_TOKEN", "")
    vk_api_version: str = os.getenv("VK_API_VERSION", "5.199")
    startup_retry_attempts: int = int(os.getenv("STARTUP_RETRY_ATTEMPTS", "30"))
    startup_retry_delay_seconds: float = float(os.getenv("STARTUP_RETRY_DELAY_SECONDS", "2"))

    # SMTP / Email
    email_from: str = os.getenv("EMAIL_FROM", "no-reply@example.com")
    email_from_name: str = os.getenv("EMAIL_FROM_NAME", "Parser Monitor")
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_use_ssl: bool = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
    smtp_starttls: bool = os.getenv("SMTP_STARTTLS", "true").lower() == "true"
    smtp_timeout_seconds: int = int(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))

    # Routing keys for auth email events
    auth_verification_routing_key: str = os.getenv("AUTH_EMAIL_VERIFICATION_ROUTING_KEY", "auth.email.verification")
    auth_password_reset_routing_key: str = os.getenv("AUTH_EMAIL_RESET_ROUTING_KEY", "auth.email.password_reset")

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


settings = Settings()
