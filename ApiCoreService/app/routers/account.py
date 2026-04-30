from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import EmailVerification, User
from app.schemas import (
    EmailConfirmRequest,
    EmailStartRequest,
    EmailStartResponse,
    MessageResponse,
    PasswordChangeRequest,
    PasswordSetRequest,
    UserPatch,
    UserRead,
)
from app.security import generate_email_code, hash_password, hash_secret, verify_password
from app.services.email import email_sender

router = APIRouter(prefix="/account", tags=["account"])


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get current account",
    description="Returns the profile of the authenticated user represented by the JWT bearer token.",
    response_description="Current user profile.",
)
async def get_me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user


@router.patch(
    "/me",
    response_model=UserRead,
    summary="Update current account profile",
    description=(
        "Updates non-authentication profile fields for the current user, such as display name "
        "and avatar URL. Email and password are managed through dedicated endpoints."
    ),
    response_description="Updated current user profile.",
)
async def update_me(
    payload: UserPatch,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if payload.username is not None:
        user.username = payload.username
    if payload.avatar_url is not None:
        user.avatar_url = payload.avatar_url
    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/email/start",
    response_model=EmailStartResponse,
    summary="Start login email verification",
    description=(
        "Starts verification for the website login email. A code is sent through the configured "
        "email sender. In development mode the response may also include `dev_code` for easier testing."
    ),
    response_description="Verification id, expiration timestamp and optional development code.",
)
async def start_email_verification(
    payload: EmailStartRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmailStartResponse:
    email = payload.email.lower()
    existing = await db.execute(select(User).where(User.login_email == email, User.id != user.id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already used")

    code = generate_email_code()
    verification = EmailVerification(
        user_id=user.id,
        email=email,
        code_hash=hash_secret(code),
        purpose="change_login_email" if user.login_email else "set_login_email",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.email_code_ttl_minutes),
    )
    db.add(verification)
    await db.commit()
    await email_sender.send_verification_code(email, code)
    return EmailStartResponse(
        verification_id=verification.id,
        expires_at=verification.expires_at,
        dev_code=code if settings.expose_dev_email_code else None,
    )


@router.post(
    "/email/confirm",
    response_model=UserRead,
    summary="Confirm login email",
    description=(
        "Confirms the code from `/account/email/start` and stores the email as `login_email`. "
        "If this is the first login email for a Telegram-created user, `password` is required in "
        "the same request because the database requires login email and password hash to be set together."
    ),
    response_description="Updated current user profile with verified login email.",
)
async def confirm_email(
    payload: EmailConfirmRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    verification = await db.get(EmailVerification, payload.verification_id)
    now = datetime.now(timezone.utc)
    if not verification or verification.user_id != user.id or verification.used_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification not found")
    if verification.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification expired")
    if verification.attempts >= verification.max_attempts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many attempts")

    verification.attempts += 1
    if verification.code_hash != hash_secret(payload.code):
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")

    if not user.password_hash:
        if not payload.password:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Password is required when setting login email for the first time",
            )
        user.password_hash = hash_password(payload.password)

    existing = await db.execute(select(User).where(User.login_email == verification.email, User.id != user.id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already used")

    user.login_email = verification.email
    user.is_email_verified = True
    verification.used_at = now
    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/password/set",
    response_model=MessageResponse,
    summary="Set first password",
    description=(
        "Sets a password for a Telegram-created account that does not yet have one. "
        "If a password already exists, use `/account/password/change` instead."
    ),
    response_description="Confirmation message.",
)
async def set_password(
    payload: PasswordSetRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    if user.password_hash:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Password is already set")
    user.password_hash = hash_password(payload.password)
    await db.commit()
    return MessageResponse(message="Password has been set")


@router.post(
    "/password/change",
    response_model=MessageResponse,
    summary="Change password",
    description="Changes the current user's password after verifying the current password.",
    response_description="Confirmation message.",
)
async def change_password(
    payload: PasswordChangeRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid current password")
    user.password_hash = hash_password(payload.new_password)
    await db.commit()
    return MessageResponse(message="Password has been changed")
