async def test_create_task_persists_and_publishes_parser_contract(client, fake_session, monkeypatch):
    published = []

    async def fake_publish(task, *, run_now=False):
        published.append((task, run_now))

    monkeypatch.setattr("app.routers.tasks.rabbitmq.publish_task_upserted", fake_publish)

    response = await client.post(
        "/tasks",
        json={
            "name": "Avito phones",
            "platform": "avito",
            "url": "https://www.avito.ru/moskva/telefony",
            "interval_minutes": 15,
            "is_active": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["platform"] == "avito"
    assert body["interval_minutes"] == 15
    assert len(fake_session.added) == 1
    assert published[0][1] is True


async def test_create_task_rejects_url_from_wrong_platform(client):
    response = await client.post(
        "/tasks",
        json={
            "name": "Wrong URL",
            "platform": "cian",
            "url": "https://www.avito.ru/moskva/telefony",
            "interval_minutes": 15,
        },
    )

    assert response.status_code == 422
