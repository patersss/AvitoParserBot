from datetime import datetime, timezone

from app.models import EmailVerification
from app.security import hash_secret


async def test_confirm_notification_email_creates_active_email_channel(client, fake_session, user):
    verification = EmailVerification(
        id=None,
        user_id=user.id,
        email="notify@example.com",
        code_hash=hash_secret("123456"),
        purpose="set_notification_email",
        attempts=0,
        max_attempts=5,
        expires_at=datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year + 1),
        used_at=None,
        created_at=datetime.now(timezone.utc),
    )
    fake_session._ensure_identity(verification)
    fake_session.verification = verification
    fake_session.execute_results = [None]

    response = await client.post(
        "/notification-channels/email/confirm",
        json={"verification_id": str(verification.id), "code": "123456"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "email"
    assert body["config"] == {"email": "notify@example.com"}
    assert body["is_active"] is True
    assert verification.used_at is not None


async def test_confirm_notification_email_rejects_invalid_code(client, fake_session, user, future_time):
    verification = EmailVerification(
        id=None,
        user_id=user.id,
        email="notify@example.com",
        code_hash=hash_secret("123456"),
        purpose="set_notification_email",
        attempts=0,
        max_attempts=5,
        expires_at=future_time,
        used_at=None,
        created_at=datetime.now(timezone.utc),
    )
    fake_session._ensure_identity(verification)
    fake_session.verification = verification

    response = await client.post(
        "/notification-channels/email/confirm",
        json={"verification_id": str(verification.id), "code": "000000"},
    )

    assert response.status_code == 400
    assert verification.attempts == 1
