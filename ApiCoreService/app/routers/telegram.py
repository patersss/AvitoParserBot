from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import verify_service_token
from app.models import LoginToken, TelegramAccount, User
from app.schemas import (
    TelegramLoginTokenRequest,
    TelegramLoginTokenResponse,
    TelegramUpsertRequest,
    TelegramUserResponse,
)
from app.security import generate_url_token, hash_secret

router = APIRouter(prefix="/telegram", tags=["telegram"], dependencies=[Depends(verify_service_token)])


@router.post(
    "/users/upsert",
    response_model=TelegramUserResponse,
    summary="Create or update Telegram-backed user",
    description=(
        "Internal BotService endpoint. Creates a user and Telegram binding on first contact, "
        "or updates Telegram username/chat metadata on repeated calls. "
        "Requires `X-Service-Token`; do not expose this endpoint directly to browsers."
    ),
    response_description="User profile with Telegram identifiers.",
)
async def upsert_telegram_user(
    payload: TelegramUpsertRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TelegramUserResponse:
    result = await db.execute(
        select(TelegramAccount).where(
            or_(
                TelegramAccount.telegram_user_id == payload.telegram_user_id,
                TelegramAccount.chat_id == payload.chat_id,
            )
        )
    )
    telegram_accounts = list(result.scalars().all())
    user_ids = {account.user_id for account in telegram_accounts}
    if len(user_ids) > 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Telegram identifiers belong to different users")
    telegram_account = telegram_accounts[0] if telegram_accounts else None

    if telegram_account:
        user = await db.get(User, telegram_account.user_id)
        telegram_account.telegram_user_id = payload.telegram_user_id
        telegram_account.chat_id = payload.chat_id
        telegram_account.username = payload.username
    else:
        user = User(username=payload.username, avatar_url=payload.avatar_url)
        db.add(user)
        await db.flush()
        telegram_account = TelegramAccount(
            user_id=user.id,
            telegram_user_id=payload.telegram_user_id,
            chat_id=payload.chat_id,
            username=payload.username,
        )
        db.add(telegram_account)

    if user is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Telegram account is inconsistent")

    user.username = payload.username or user.username
    user.avatar_url = payload.avatar_url or user.avatar_url
    await db.commit()
    await db.refresh(user)
    return TelegramUserResponse(user=user, telegram_user_id=telegram_account.telegram_user_id, chat_id=telegram_account.chat_id)


@router.post(
    "/login-token",
    response_model=TelegramLoginTokenResponse,
    summary="Create one-time website login token for Telegram user",
    description=(
        "Internal BotService endpoint. Generates a short-lived, one-time token that can be embedded "
        "into a website login link. Only the token hash is stored in the database. "
        "The raw token is returned once and later exchanged through `/auth/telegram-token`."
    ),
    response_description="Raw one-time token and expiration timestamp.",
)
async def create_login_token(
    payload: TelegramLoginTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TelegramLoginTokenResponse:
    if payload.telegram_user_id is None and payload.chat_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="telegram_user_id or chat_id is required")

    filters = []
    if payload.telegram_user_id is not None:
        filters.append(TelegramAccount.telegram_user_id == payload.telegram_user_id)
    if payload.chat_id is not None:
        filters.append(TelegramAccount.chat_id == payload.chat_id)

    result = await db.execute(select(TelegramAccount).where(or_(*filters)))
    telegram_account = result.scalar_one_or_none()
    if not telegram_account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Telegram account not found")

    user = await db.get(User, telegram_account.user_id)
    if not user or user.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.status == "banned":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is banned")

    raw_token = generate_url_token()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.telegram_login_token_ttl_minutes)
    db.add(
        LoginToken(
            token_hash=hash_secret(raw_token),
            user_id=user.id,
            purpose="telegram_site_login",
            expires_at=expires_at,
        )
    )
    await db.commit()
    return TelegramLoginTokenResponse(token=raw_token, expires_at=expires_at)
