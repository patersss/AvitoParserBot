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
    db_name: str = os.getenv("DB_NAME", "avito_parser")
    db_echo: bool = os.getenv("DB_ECHO", "false").lower() == "true"

    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-production")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

    service_api_token: str = os.getenv("SERVICE_API_TOKEN", "dev-service-token")

    rabbitmq_url: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    parser_task_events_queue: str = os.getenv("PARSER_TASK_EVENTS_QUEUE", "parser.task_events")
    notification_exchange: str = os.getenv("NOTIFICATION_EXCHANGE", "notification.events")
    listing_found_routing_key: str = os.getenv("LISTING_FOUND_ROUTING_KEY", "listing.found")
    api_listing_found_queue: str = os.getenv("API_LISTING_FOUND_QUEUE", "api.listing_found")
    startup_retry_attempts: int = int(os.getenv("STARTUP_RETRY_ATTEMPTS", "30"))
    startup_retry_delay_seconds: float = float(os.getenv("STARTUP_RETRY_DELAY_SECONDS", "2"))

    telegram_login_token_ttl_minutes: int = int(os.getenv("TELEGRAM_LOGIN_TOKEN_TTL_MINUTES", "15"))
    email_code_ttl_minutes: int = int(os.getenv("EMAIL_CODE_TTL_MINUTES", "15"))
    expose_dev_email_code: bool = os.getenv("EXPOSE_DEV_EMAIL_CODE", "true").lower() == "true"

    email_from: str = os.getenv("EMAIL_FROM", "no-reply@example.com")
    email_from_name: str = os.getenv("EMAIL_FROM_NAME", "Parser Monitor")
    smtp_host: str | None = os.getenv("SMTP_HOST") or None
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str | None = os.getenv("SMTP_USERNAME") or None
    smtp_password: str | None = os.getenv("SMTP_PASSWORD") or None
    smtp_use_ssl: bool = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
    smtp_starttls: bool = os.getenv("SMTP_STARTTLS", "true").lower() == "true"
    smtp_timeout_seconds: float = float(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
