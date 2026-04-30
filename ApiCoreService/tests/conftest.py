from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.dependencies import get_current_user
from app.main import app
from app.models import EmailVerification, ListingHistory, LoginToken, NotificationChannel, Task, User


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        if isinstance(self.value, list):
            return self.value[0] if self.value else None
        return self.value

    def scalar_one(self):
        value = self.scalar_one_or_none()
        if value is None:
            raise AssertionError("Expected one scalar result")
        return value

    def scalars(self):
        return self

    def all(self):
        if isinstance(self.value, list):
            return self.value
        if self.value is None:
            return []
        return [self.value]


class FakeSession:
    def __init__(
        self,
        *,
        user: User | None = None,
        token: LoginToken | None = None,
        verification: EmailVerification | None = None,
        task: Task | None = None,
        execute_results: list | None = None,
    ) -> None:
        self.user = user
        self.token = token
        self.verification = verification
        self.task = task
        self.execute_results = list(execute_results or [])
        self.added = []
        self.commits = 0
        self.refreshed = []

    def add(self, instance) -> None:
        self._ensure_identity(instance)
        self.added.append(instance)

    async def flush(self) -> None:
        for instance in self.added:
            self._ensure_identity(instance)

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, instance) -> None:
        self._ensure_identity(instance)
        self.refreshed.append(instance)

    async def get(self, model, key):
        if model is LoginToken and self.token and key == self.token.token_hash:
            return self.token
        if model is User:
            if self.user and key == self.user.id:
                return self.user
            if self.user and getattr(self.user, "target_user", None) and key == self.user.target_user.id:
                return self.user.target_user
        if model is EmailVerification and self.verification and key == self.verification.id:
            return self.verification
        if model is Task and self.task and key == self.task.id:
            return self.task
        return None

    async def execute(self, _statement):
        if self.execute_results:
            return FakeResult(self.execute_results.pop(0))
        return FakeResult(None)

    def _ensure_identity(self, instance) -> None:
        now = datetime.now(timezone.utc)
        if isinstance(instance, (User, Task, EmailVerification, NotificationChannel, ListingHistory)):
            if getattr(instance, "id", None) is None:
                instance.id = uuid4()
        if isinstance(instance, (User, Task, NotificationChannel)):
            if getattr(instance, "created_at", None) is None:
                instance.created_at = now
            if getattr(instance, "updated_at", None) is None:
                instance.updated_at = now
        if isinstance(instance, EmailVerification):
            if getattr(instance, "created_at", None) is None:
                instance.created_at = now
        if isinstance(instance, ListingHistory):
            if getattr(instance, "created_at", None) is None:
                instance.created_at = now


def make_user(*, role: str = "user", status: str = "active") -> User:
    return User(
        id=uuid4(),
        username="tester",
        avatar_url=None,
        login_email="tester@example.com",
        password_hash=None,
        is_email_verified=True,
        user_role=role,
        status=status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        deleted_at=None,
    )


def make_task(user_id: UUID) -> Task:
    return Task(
        id=uuid4(),
        user_id=user_id,
        name="Avito phones",
        platform="avito",
        url="https://www.avito.ru/moskva/telefony",
        interval_minutes=30,
        end_date=None,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        deleted_at=None,
    )


def make_listing(user_id: UUID, task_id: UUID) -> ListingHistory:
    return ListingHistory(
        id=uuid4(),
        user_id=user_id,
        task_id=task_id,
        platform="avito",
        external_id="external-1",
        title="Phone",
        price=1000,
        url="https://www.avito.ru/item/1",
        image_url=None,
        published_at=None,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def user() -> User:
    return make_user()


@pytest.fixture
def fake_session(user: User) -> FakeSession:
    return FakeSession(user=user)


@pytest.fixture
async def client(fake_session: FakeSession, user: User) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield fake_session

    async def override_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
    app.dependency_overrides.clear()


@pytest.fixture
def future_time() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=15)
