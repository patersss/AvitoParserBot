import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import account, admin, auth, listings, notification_channels, tasks, telegram
from app.services.rabbitmq import rabbitmq

OPENAPI_DESCRIPTION = """
ApiCoreService is the central REST API for the parser product.

Main responsibilities:

- receives requests from website and Telegram bot frontends;
- owns users, Telegram bindings, parsing tasks and found listings history;
- sends task changes to parserService through RabbitMQ;
- receives `listing.found` events from parserService and stores them for frontend reads;
- manages account settings, password/email setup and notification channels;
- exposes admin operations for user moderation and task inspection.

Registration model:

- public website registration is intentionally disabled;
- a user is created by BotService through Telegram endpoints;
- BotService creates a one-time site login token;
- the website exchanges that token for a JWT access token;
- after that the user may set email and password for regular website login.

Authentication:

- user-facing endpoints use `Authorization: Bearer <jwt>`;
- Telegram service endpoints use `X-Service-Token: <SERVICE_API_TOKEN>`;
- admin endpoints require JWT of a user with role `admin` or `superadmin`.
"""

TAGS_METADATA = [
    {
        "name": "auth",
        "description": "Website authentication. There is no public registration; first login must come from Telegram one-time token.",
    },
    {
        "name": "account",
        "description": "Current user profile, login email confirmation and password management.",
    },
    {
        "name": "telegram",
        "description": "Internal BotService endpoints protected by `X-Service-Token`. Used to create Telegram-backed users and one-time site login tokens.",
    },
    {
        "name": "tasks",
        "description": "User-owned parsing task management. Create/update/delete actions publish RabbitMQ messages for parserService.",
    },
    {
        "name": "listings",
        "description": "Read found listings saved from parserService `listing.found` events.",
    },
    {
        "name": "notification-channels",
        "description": "Website notification channel settings. Email is confirmed here; Telegram is expected to be created by BotService.",
    },
    {
        "name": "admin",
        "description": "Administrative moderation and cross-user task/listing inspection.",
    },
    {
        "name": "system",
        "description": "Service health and operational endpoints.",
    },
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def retry_startup_step(name: str, step):
    for attempt in range(1, settings.startup_retry_attempts + 1):
        try:
            return await step()
        except Exception:
            if attempt >= settings.startup_retry_attempts:
                raise
            logger.warning(
                "%s is not ready yet; retrying in %s seconds (%s/%s)",
                name,
                settings.startup_retry_delay_seconds,
                attempt,
                settings.startup_retry_attempts,
            )
            await asyncio.sleep(settings.startup_retry_delay_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await retry_startup_step("Database", init_db)
    try:
        await retry_startup_step("RabbitMQ", rabbitmq.connect)
        await rabbitmq.start_listing_consumer()
    except Exception:
        logger.exception("RabbitMQ is unavailable. API will start, but parser synchronization is disabled.")
    yield
    await rabbitmq.close()


app = FastAPI(
    title="ApiCoreService",
    version="0.1.0",
    description=OPENAPI_DESCRIPTION,
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(account.router)
app.include_router(telegram.router)
app.include_router(tasks.router)
app.include_router(listings.router)
app.include_router(notification_channels.router)
app.include_router(admin.router)


@app.get(
    "/health",
    tags=["system"],
    summary="Health check",
    description="Returns a small success payload when the FastAPI process is alive.",
)
async def health() -> dict[str, str]:
    return {"status": "ok"}
