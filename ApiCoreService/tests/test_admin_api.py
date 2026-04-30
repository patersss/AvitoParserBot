from app.database import get_db
from app.dependencies import get_current_user
from app.main import app
from tests.conftest import FakeSession, make_user


async def test_regular_user_cannot_access_admin_routes(client):
    response = await client.get("/admin/users")

    assert response.status_code == 403


async def test_admin_cannot_ban_superadmin():
    admin = make_user(role="admin")
    target = make_user(role="superadmin")
    admin.target_user = target
    fake_session = FakeSession(user=admin)

    async def override_get_db():
        yield fake_session

    async def override_current_user():
        return admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.patch(f"/admin/users/{target.id}/ban", json={})

    app.dependency_overrides.clear()
    assert response.status_code == 403


async def test_admin_can_ban_regular_user():
    admin = make_user(role="admin")
    target = make_user(role="user")
    admin.target_user = target
    fake_session = FakeSession(user=admin)

    async def override_get_db():
        yield fake_session

    async def override_current_user():
        return admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.patch(f"/admin/users/{target.id}/ban", json={})

    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert target.status == "banned"
