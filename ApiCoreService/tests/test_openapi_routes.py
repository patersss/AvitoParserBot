from app.main import app


def test_openapi_contains_expected_route_groups():
    paths = set(app.openapi()["paths"])

    assert "/auth/register" not in paths
    assert "/auth/login" in paths
    assert "/auth/telegram-token" in paths
    assert "/tasks" in paths
    assert "/tasks/{task_id}/listings" in paths
    assert "/listings" in paths
    assert "/admin/users/{user_id}/ban" in paths
    assert "/notification-channels" in paths
    assert "/notification-channels/email/start" in paths
    assert "/notification-channels/email/confirm" in paths
