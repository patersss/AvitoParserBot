from datetime import datetime, timezone

from app.models import LoginToken
from app.security import hash_secret


async def test_telegram_login_token_is_one_time(client, fake_session, user, future_time):
    raw_token = "telegram-login-token-value"
    fake_session.token = LoginToken(
        token_hash=hash_secret(raw_token),
        user_id=user.id,
        purpose="telegram_site_login",
        expires_at=future_time,
        used_at=None,
        created_at=datetime.now(timezone.utc),
    )

    response = await client.post("/auth/telegram-token", json={"token": raw_token})

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert fake_session.token.used_at is not None

    second_response = await client.post("/auth/telegram-token", json={"token": raw_token})

    assert second_response.status_code == 401


async def test_expired_telegram_login_token_is_rejected(client, fake_session, user):
    raw_token = "expired-telegram-login-token-value"
    fake_session.token = LoginToken(
        token_hash=hash_secret(raw_token),
        user_id=user.id,
        purpose="telegram_site_login",
        expires_at=datetime.now(timezone.utc),
        used_at=None,
        created_at=datetime.now(timezone.utc),
    )

    response = await client.post("/auth/telegram-token", json={"token": raw_token})

    assert response.status_code == 401
