from tests.conftest import make_listing, make_task


async def test_task_listings_are_returned_after_task_ownership_check(client, fake_session, user):
    task = make_task(user.id)
    listing = make_listing(user.id, task.id)
    fake_session.execute_results = [task, [listing]]

    response = await client.get(f"/tasks/{task.id}/listings")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["task_id"] == str(task.id)
    assert body[0]["external_id"] == "external-1"


async def test_global_listings_endpoint_supports_user_scoped_results(client, fake_session, user):
    task = make_task(user.id)
    listing = make_listing(user.id, task.id)
    fake_session.execute_results = [[listing]]

    response = await client.get("/listings", params={"platform": "avito"})

    assert response.status_code == 200
    assert response.json()[0]["platform"] == "avito"
