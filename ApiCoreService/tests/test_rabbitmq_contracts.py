import json
from datetime import datetime, timezone
from uuid import uuid4

from app.models import Task
from app.services.rabbitmq import (
    RabbitMQClient,
    build_task_deleted_payload,
    build_task_upserted_payload,
    listing_found_to_history_values,
)


def test_task_upserted_payload_matches_parser_service_contract():
    now = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    task = Task(
        id=uuid4(),
        user_id=uuid4(),
        name="Avito phones",
        platform="avito",
        url="https://www.avito.ru/moskva/telefony",
        interval_minutes=30,
        end_date=None,
        is_active=True,
    )

    payload = build_task_upserted_payload(task, run_now=True, now=now)

    assert payload["event_type"] == "task.upserted"
    assert payload["source_service"] == "ApiCoreService"
    assert payload["payload"]["task_id"] == str(task.id)
    assert payload["payload"]["user_id"] == str(task.user_id)
    assert payload["payload"]["platform"] == "avito"
    assert payload["payload"]["interval_minutes"] == 30
    assert payload["payload"]["next_run_at"] == now.isoformat()


def test_task_deleted_payload_matches_parser_service_contract():
    task_id = uuid4()

    payload = build_task_deleted_payload(task_id)

    assert payload == {
        "event_type": "task.deleted",
        "source_service": "ApiCoreService",
        "payload": {"task_id": str(task_id)},
    }


def test_listing_found_payload_maps_to_history_values():
    user_id = uuid4()
    task_id = uuid4()

    values = listing_found_to_history_values(
        {
            "event_type": "listing.found",
            "source_service": "parsingService",
            "user_id": str(user_id),
            "task_id": str(task_id),
            "listing": {
                "platform": "avito",
                "external_id": "123",
                "title": "Phone",
                "price": 1000,
                "url": "https://www.avito.ru/item/123",
                "image_url": None,
                "published_at": "2026-04-30T12:00:00+00:00",
                "created_at": "2026-04-30T12:01:00+00:00",
            },
        }
    )

    assert values["user_id"] == user_id
    assert values["task_id"] == task_id
    assert values["platform"] == "avito"
    assert values["external_id"] == "123"
    assert values["published_at"].tzinfo is not None


class FakeMessage:
    def __init__(self, body: bytes):
        self.body = body
        self.acked = False
        self.rejected = None

    async def ack(self):
        self.acked = True

    async def reject(self, *, requeue: bool):
        self.rejected = requeue


async def test_listing_consumer_acks_valid_message(monkeypatch):
    client = RabbitMQClient()
    saved = []

    async def fake_save(payload):
        saved.append(payload)

    monkeypatch.setattr(client, "_save_listing", fake_save)
    message = FakeMessage(json.dumps({"event_type": "listing.found"}).encode("utf-8"))

    await client._on_listing_found(message)

    assert message.acked is True
    assert message.rejected is None
    assert saved == [{"event_type": "listing.found"}]


async def test_listing_consumer_rejects_invalid_json():
    client = RabbitMQClient()
    message = FakeMessage(b"not-json")

    await client._on_listing_found(message)

    assert message.acked is False
    assert message.rejected is False
