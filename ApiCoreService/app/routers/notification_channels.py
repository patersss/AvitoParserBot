import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import EmailVerification, NotificationChannel, User
from app.schemas import (
    EmailStartResponse,
    MessageResponse,
    NotificationChannelRead,
    NotificationChannelType,
    NotificationChannelUpdate,
    NotificationEmailConfirmRequest,
    NotificationEmailStartRequest,
)
from app.security import generate_email_code, hash_secret
from app.services.email import email_sender
from app.services.rabbitmq import rabbitmq

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notification-channels", tags=["notification-channels"])


@router.get(
    "",
    response_model=list[NotificationChannelRead],
    summary="List notification channels",
    description=(
        "Returns notification channels configured for the authenticated user. "
        "Email channels are configured through this API; Telegram channels are expected to be created by BotService."
    ),
    response_description="Configured notification channels.",
)
async def list_notification_channels(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    include_deleted: bool = False,
) -> list[NotificationChannel]:
    conditions = [NotificationChannel.user_id == user.id]
    if not include_deleted:
        conditions.append(NotificationChannel.deleted_at.is_(None))
    result = await db.execute(select(NotificationChannel).where(*conditions).order_by(NotificationChannel.created_at.asc()))
    return list(result.scalars().all())


@router.get(
    "/{channel_type}",
    response_model=NotificationChannelRead,
    summary="Get notification channel by type",
    description="Returns one active, non-deleted notification channel for the authenticated user.",
    response_description="Requested notification channel.",
)
async def get_notification_channel(
    channel_type: NotificationChannelType,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationChannel:
    return await _get_user_channel(db, user, channel_type)


@router.patch(
    "/id/{channel_id}",
    response_model=NotificationChannelRead,
    summary="Enable or disable notification channel by ID",
    description="Updates the `is_active` flag for a specific channel identified by its UUID.",
    response_description="Updated notification channel.",
)
async def update_notification_channel_by_id(
    channel_id: UUID,
    payload: NotificationChannelUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationChannel:
    channel = await db.get(NotificationChannel, channel_id)
    if not channel or channel.user_id != user.id or channel.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification channel not found")
    channel.is_active = payload.is_active
    await db.commit()
    await db.refresh(channel)
    try:
        await rabbitmq.publish_channel_upserted(channel, user.id)
    except Exception:
        logger.exception("Failed to publish channel.upserted for channel %s", channel.id)
    return channel


@router.delete(
    "/id/{channel_id}",
    response_model=MessageResponse,
    summary="Delete notification channel by ID",
    description="Soft-deletes a notification channel by setting `deleted_at` and `is_active=false`.",
    response_description="Confirmation message.",
)
async def delete_notification_channel_by_id(
    channel_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    channel = await db.get(NotificationChannel, channel_id)
    if not channel or channel.user_id != user.id or channel.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification channel not found")
    channel.is_active = False
    channel.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    try:
        await rabbitmq.publish_channel_deleted(channel.id, user.id, channel.type)
    except Exception:
        logger.exception("Failed to publish channel.deleted for channel %s", channel.id)
    return MessageResponse(message="Notification channel has been disabled")


@router.patch(
    "/{channel_type}",
    response_model=NotificationChannelRead,
    summary="Enable or disable notification channel by type",
    description=(
        "Updates the `is_active` flag for an existing channel. This is useful for pausing "
        "notifications without losing channel configuration."
    ),
    response_description="Updated notification channel.",
)
async def update_notification_channel(
    channel_type: NotificationChannelType,
    payload: NotificationChannelUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationChannel:
    channel = await _get_user_channel(db, user, channel_type)
    channel.is_active = payload.is_active
    channel.deleted_at = None
    await db.commit()
    await db.refresh(channel)
    try:
        await rabbitmq.publish_channel_upserted(channel, user.id)
    except Exception:
        logger.exception("Failed to publish channel.upserted for channel %s", channel.id)
    return channel


@router.delete(
    "/{channel_type}",
    response_model=MessageResponse,
    summary="Disable notification channel by type",
    description=(
        "Soft-deletes a notification channel by setting `deleted_at` and `is_active=false`. "
        "The channel can later be recreated by confirming email again."
    ),
    response_description="Confirmation message.",
)
async def delete_notification_channel(
    channel_type: NotificationChannelType,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    channel = await _get_user_channel(db, user, channel_type)
    channel.is_active = False
    channel.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    try:
        await rabbitmq.publish_channel_deleted(channel.id, user.id, channel.type)
    except Exception:
        logger.exception("Failed to publish channel.deleted for channel %s", channel.id)
    return MessageResponse(message="Notification channel has been disabled")


@router.post(
    "/email/start",
    response_model=EmailStartResponse,
    summary="Start notification email verification",
    description=(
        "Starts email confirmation for notification delivery. This does not change the login email; "
        "it creates an `email_verifications` row with purpose `set_notification_email`."
    ),
    response_description="Verification id, expiration timestamp and optional development code.",
)
async def start_notification_email_verification(
    payload: NotificationEmailStartRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmailStartResponse:
    code = generate_email_code()
    verification = EmailVerification(
        user_id=user.id,
        email=payload.email.lower(),
        code_hash=hash_secret(code),
        purpose="set_notification_email",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.email_code_ttl_minutes),
    )
    db.add(verification)
    await db.commit()
    await email_sender.send_verification_code(verification.email, code)
    return EmailStartResponse(
        verification_id=verification.id,
        expires_at=verification.expires_at,
        dev_code=code if settings.expose_dev_email_code else None,
    )


@router.post(
    "/email/confirm",
    response_model=NotificationChannelRead,
    summary="Confirm notification email channel",
    description=(
        "Confirms the code from `/notification-channels/email/start` and creates a new "
        "email notification channel with config `{email: ...}`. Each email gets its own channel record."
    ),
    response_description="Created email notification channel.",
)
async def confirm_notification_email(
    payload: NotificationEmailConfirmRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationChannel:
    verification = await db.get(EmailVerification, payload.verification_id)
    now = datetime.now(timezone.utc)
    if not verification or verification.user_id != user.id or verification.purpose != "set_notification_email":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification not found")
    if verification.used_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification already used")
    if verification.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification expired")
    if verification.attempts >= verification.max_attempts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many attempts")

    verification.attempts += 1
    if verification.code_hash != hash_secret(payload.code):
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")

    duplicate = await _find_user_channel_by_email(db, user, verification.email)
    if duplicate:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This email is already added as a notification channel")

    channel = NotificationChannel(
        user_id=user.id,
        type="email",
        config={"email": verification.email},
        is_active=True,
    )
    db.add(channel)
    verification.used_at = now
    await db.commit()
    await db.refresh(channel)

    try:
        await rabbitmq.publish_channel_upserted(channel, user.id)
    except Exception:
        logger.exception("Failed to publish channel.upserted for channel %s", channel.id)

    return channel


async def _get_user_channel(
    db: AsyncSession,
    user: User,
    channel_type: NotificationChannelType,
) -> NotificationChannel:
    channel = await _find_user_channel(db, user, channel_type, include_deleted=False)
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification channel not found")
    return channel


async def _find_user_channel(
    db: AsyncSession,
    user: User,
    channel_type: NotificationChannelType,
    *,
    include_deleted: bool,
) -> NotificationChannel | None:
    conditions = [NotificationChannel.user_id == user.id, NotificationChannel.type == channel_type]
    if not include_deleted:
        conditions.append(NotificationChannel.deleted_at.is_(None))
    result = await db.execute(select(NotificationChannel).where(*conditions).order_by(NotificationChannel.created_at.asc()))
    return result.scalars().first()


async def _find_user_channel_by_email(
    db: AsyncSession,
    user: User,
    email: str,
) -> NotificationChannel | None:
    result = await db.execute(
        select(NotificationChannel).where(
            NotificationChannel.user_id == user.id,
            NotificationChannel.type == "email",
            NotificationChannel.deleted_at.is_(None),
            NotificationChannel.config["email"].astext == email,
        )
    )
    return result.scalars().first()
