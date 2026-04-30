from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


Platform = Literal["avito", "cian", "youla"]
UserRole = Literal["user", "admin", "superadmin"]
UserStatus = Literal["active", "banned", "deleted"]
NotificationChannelType = Literal["telegram", "email", "vk"]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str | None = None
    avatar_url: str | None = None
    login_email: str | None = None
    is_email_verified: bool
    user_role: UserRole
    status: UserStatus
    created_at: datetime


class AuthToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "email": "user@example.com",
                    "password": "StrongPassword123",
                }
            ]
        }
    )

    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class TelegramUpsertRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "telegram_user_id": 123456789,
                    "chat_id": 123456789,
                    "username": "telegram_user",
                    "avatar_url": "https://example.com/avatar.png",
                }
            ]
        }
    )

    telegram_user_id: int
    chat_id: int
    username: str | None = Field(default=None, max_length=100)
    avatar_url: str | None = None


class TelegramUserResponse(BaseModel):
    user: UserRead
    telegram_user_id: int
    chat_id: int


class TelegramLoginTokenRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"telegram_user_id": 123456789},
                {"chat_id": 123456789},
            ]
        }
    )

    telegram_user_id: int | None = None
    chat_id: int | None = None


class TelegramLoginTokenResponse(BaseModel):
    token: str
    expires_at: datetime


class TelegramTokenLoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"token": "one-time-token-from-telegram-bot"},
            ]
        }
    )

    token: str = Field(min_length=16, max_length=256)


class EmailStartRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"email": "user@example.com"}]})

    email: EmailStr


class EmailStartResponse(BaseModel):
    verification_id: UUID
    expires_at: datetime
    dev_code: str | None = None


class EmailConfirmRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "verification_id": "8b049fed-9647-41b6-9e4a-0f2c1f6bf7f6",
                    "code": "123456",
                    "password": "StrongPassword123",
                }
            ]
        }
    )

    verification_id: UUID
    code: str = Field(min_length=4, max_length=12)
    password: str | None = Field(default=None, min_length=8, max_length=256)


class PasswordSetRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"password": "StrongPassword123"}]})

    password: str = Field(min_length=8, max_length=256)


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "current_password": "OldStrongPassword123",
                    "new_password": "NewStrongPassword123",
                }
            ]
        }
    )

    current_password: str = Field(min_length=8, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class TaskBase(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Avito phones in Moscow",
                    "platform": "avito",
                    "url": "https://www.avito.ru/moskva/telefony",
                    "interval_minutes": 30,
                    "end_date": "2026-05-30T12:00:00+03:00",
                    "is_active": True,
                }
            ]
        }
    )

    name: str | None = Field(default=None, max_length=150)
    platform: Platform
    url: str = Field(min_length=8, max_length=4096)
    interval_minutes: int = Field(default=30, gt=0)
    end_date: datetime | None = None
    is_active: bool = True

    @field_validator("url")
    @classmethod
    def validate_platform_url(cls, value: str, info):
        platform = info.data.get("platform")
        if platform == "avito" and "avito.ru" not in value:
            raise ValueError("Avito task URL must contain avito.ru")
        if platform == "cian" and "cian.ru" not in value:
            raise ValueError("Cian task URL must contain cian.ru")
        if platform == "youla" and "youla.ru" not in value:
            raise ValueError("Youla task URL must contain youla.ru")
        return value


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Avito phones, faster checks",
                    "interval_minutes": 15,
                    "is_active": True,
                }
            ]
        }
    )

    name: str | None = Field(default=None, max_length=150)
    platform: Platform | None = None
    url: str | None = Field(default=None, min_length=8, max_length=4096)
    interval_minutes: int | None = Field(default=None, gt=0)
    end_date: datetime | None = None
    is_active: bool | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str | None
    platform: Platform
    url: str
    interval_minutes: int
    end_date: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class ListingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    task_id: UUID
    platform: Platform
    external_id: str
    title: str
    price: int | None
    url: str
    image_url: str | None
    published_at: datetime | None
    created_at: datetime


class NotificationChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    type: NotificationChannelType
    config: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class NotificationChannelUpdate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"is_active": False}]})

    is_active: bool


class NotificationEmailStartRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"email": "notifications@example.com"}]})

    email: EmailStr


class NotificationEmailConfirmRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "verification_id": "8b049fed-9647-41b6-9e4a-0f2c1f6bf7f6",
                    "code": "123456",
                }
            ]
        }
    )

    verification_id: UUID
    code: str = Field(min_length=4, max_length=12)


class UserPatch(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "username": "new_display_name",
                    "avatar_url": "https://example.com/avatar.png",
                }
            ]
        }
    )

    username: str | None = Field(default=None, max_length=150)
    avatar_url: str | None = None


class AdminBanRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"reason": "Spam or abuse"}]})

    reason: str | None = Field(default=None, max_length=500)


class MessageResponse(BaseModel):
    message: str
