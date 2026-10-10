import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from freight_ecommerce.config import Settings
from freight_ecommerce.domain import models as m
from freight_ecommerce.main import create_app

pytestmark = [pytest.mark.postgres, pytest.mark.anyio]
SECRET = "synthetic-independent-webhook-signing-secret"
ADMIN_KEY = "synthetic-local-admin-key-for-tests-only"
ADMIN_HEADERS = {"X-Local-Admin-Key": ADMIN_KEY}
COMPANY = UUID("00000000-0000-4000-8000-000000000002")
LOCATION = UUID("00000000-0000-4000-8000-000000000003")
SHIPMENT = "synthetic-native-shipment-001"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def webhook_app(db_engine):
    settings = Settings(
        _env_file=None,
        environment="test",
        LOCAL_ADMIN_KEY=ADMIN_KEY,
        PACKSENVIOS_WEBHOOK_SECRET=SECRET,
        PACKSENVIOS_WEBHOOK_TIMESTAMP_FORMAT="unix_seconds",
        FREIGHT_COMPANY_ID=str(COMPANY),
        FREIGHT_LOCATION_ID=str(LOCATION),
    )
    app = create_app(settings, engine=db_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://shop.test") as http:
        yield http, db_engine, app
    await http.aclose()


def webhook_body(
    *, event_id="synthetic-event-001", occurred_at=None, event_type="shipment.tracking_updated"
):
    when = occurred_at or datetime.now(UTC)
    payload = {
        "version": 1,
        "id": event_id,
        "type": event_type,
        "occurredAt": when.isoformat(),
        "companyId": str(COMPANY),
        "locationId": str(LOCATION),
        "data": {
            "shipmentId": SHIPMENT,
            "publicCode": "synthetic-public-code",
            "dispatchStatus": "synthetic-queued",
        },
    }
    # Whitespace is deliberate: the signature must cover these exact bytes.
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    timestamp = str(int(datetime.now(UTC).timestamp()))
    signature = (
        "v1="
        + hmac.new(
            SECRET.encode(), timestamp.encode("ascii") + b"." + body, hashlib.sha256
        ).hexdigest()
    )
    headers = {
        "Content-Type": "application/json",
        "X-Packsenvios-Timestamp": timestamp,
        "X-Packsenvios-Signature": signature,
        "X-Packsenvios-Delivery": event_id,
    }
    return body, headers


async def test_valid_exact_body_is_persisted_before_202_and_replay_is_deduplicated(webhook_app):
    http, db, app = webhook_app
    notifications = []

    async def notifier(receipt_id):
        notifications.append(receipt_id)

    app.state.webhook_reconciliation_notifier = notifier
    body, headers = webhook_body(event_type="shipment.labels_updated")
    received = await http.post("/api/webhooks/packsenvios", content=body, headers=headers)
    assert received.status_code == 202, received.text
    assert received.json() == {
        "status": "accepted",
        "event_id": "synthetic-event-001",
        "reconciliation_status": "reconciliation_pending",
        "worker_status": "notified",
        "out_of_order": False,
    }
    with Session(db) as session:
        row = session.scalar(
            select(m.WebhookReceipt).where(m.WebhookReceipt.event_id == "synthetic-event-001")
        )
        assert row is not None
        assert row.body_sha256 == hashlib.sha256(body).hexdigest()
        assert row.payload["type"] == "shipment.labels_updated"
        assert row.reconciliation_status == "reconciliation_pending"
        assert row.worker_status == "notified"
    replay = await http.post("/api/webhooks/packsenvios", content=body, headers=headers)
    assert replay.status_code == 200
    assert replay.json()["status"] == "duplicate"
    assert len(notifications) == 1
    different_body = body + b" "
    timestamp = str(int(datetime.now(UTC).timestamp()))
    different_signature = (
        "v1="
        + hmac.new(
            SECRET.encode(), timestamp.encode("ascii") + b"." + different_body, hashlib.sha256
        ).hexdigest()
    )
    conflict = await http.post(
        "/api/webhooks/packsenvios",
        content=different_body,
        headers={
            **headers,
            "X-Packsenvios-Timestamp": timestamp,
            "X-Packsenvios-Signature": different_signature,
        },
    )
    assert conflict.status_code == 409
    different_body = body + b" "
    new_timestamp = str(int(datetime.now(UTC).timestamp()))
    different_signature = (
        "v1="
        + hmac.new(
            SECRET.encode(),
            new_timestamp.encode("ascii") + b"." + different_body,
            hashlib.sha256,
        ).hexdigest()
    )
    conflict = await http.post(
        "/api/webhooks/packsenvios",
        content=different_body,
        headers={
            **headers,
            "X-Packsenvios-Timestamp": new_timestamp,
            "X-Packsenvios-Signature": different_signature,
        },
    )
    assert conflict.status_code == 409
    with Session(db) as session:
        assert session.scalar(select(func.count()).select_from(m.WebhookReceipt)) == 1


async def test_invalid_signature_stale_timestamp_and_wrong_delivery_do_not_persist(webhook_app):
    http, db, _ = webhook_app
    body, headers = webhook_body()
    tampered = dict(headers, **{"X-Packsenvios-Signature": "v1=" + "0" * 64})
    invalid = await http.post("/api/webhooks/packsenvios", content=body, headers=tampered)
    assert invalid.status_code == 401
    assert invalid.json()["detail"]["code"] == "webhook_unauthorized"

    old_timestamp = str(int((datetime.now(UTC) - timedelta(minutes=6)).timestamp()))
    old_signature = (
        "v1="
        + hmac.new(
            SECRET.encode(), old_timestamp.encode() + b"." + body, hashlib.sha256
        ).hexdigest()
    )
    stale = await http.post(
        "/api/webhooks/packsenvios",
        content=body,
        headers={
            **headers,
            "X-Packsenvios-Timestamp": old_timestamp,
            "X-Packsenvios-Signature": old_signature,
        },
    )
    assert stale.status_code == 401

    mismatch = await http.post(
        "/api/webhooks/packsenvios",
        content=body,
        headers={**headers, "X-Packsenvios-Delivery": "synthetic-other-event"},
    )
    assert mismatch.status_code == 400
    with Session(db) as session:
        assert session.scalar(select(func.count()).select_from(m.WebhookReceipt)) == 0


async def test_out_of_order_event_is_persisted_as_pending_signal_not_applied(webhook_app):
    http, db, _ = webhook_app
    later_body, later_headers = webhook_body(
        event_id="synthetic-event-later", occurred_at=datetime.now(UTC)
    )
    first = await http.post("/api/webhooks/packsenvios", content=later_body, headers=later_headers)
    assert first.status_code == 202 and first.json()["out_of_order"] is False
    assert first.json()["worker_status"] == "not_configured"

    earlier_body, earlier_headers = webhook_body(
        event_id="synthetic-event-earlier",
        occurred_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    second = await http.post(
        "/api/webhooks/packsenvios", content=earlier_body, headers=earlier_headers
    )
    assert second.status_code == 202 and second.json()["out_of_order"] is True
    with Session(db) as session:
        receipts = session.scalars(
            select(m.WebhookReceipt).order_by(m.WebhookReceipt.occurred_at)
        ).all()
        assert [item.event_id for item in receipts] == [
            "synthetic-event-earlier",
            "synthetic-event-later",
        ]
        assert receipts[0].out_of_order is True
        assert all(item.reconciliation_status == "reconciliation_pending" for item in receipts)


async def test_worker_unavailable_keeps_receipt_durable_and_pending(webhook_app):
    http, db, app = webhook_app

    async def unavailable(_receipt_id):
        raise RuntimeError("synthetic worker unavailable")

    app.state.webhook_reconciliation_notifier = unavailable
    body, headers = webhook_body(event_id="synthetic-worker-event")
    response = await http.post("/api/webhooks/packsenvios", content=body, headers=headers)
    assert response.status_code == 202
    assert response.json()["worker_status"] == "unavailable"
    with Session(db) as session:
        receipt = session.scalar(
            select(m.WebhookReceipt).where(m.WebhookReceipt.event_id == "synthetic-worker-event")
        )
        assert receipt is not None
        assert receipt.reconciliation_status == "reconciliation_pending"
        assert receipt.worker_status == "unavailable"
    pending = await http.get("/api/admin/webhooks/receipts", headers=ADMIN_HEADERS)
    assert pending.status_code == 200 and pending.json()["total"] == 1
    assert pending.json()["items"][0]["event_id"] == "synthetic-worker-event"


async def test_unconfigured_receiver_and_company_context_are_rejected(db_engine):
    unconfigured = create_app(Settings(_env_file=None, environment="test"), engine=db_engine)
    async with AsyncClient(
        transport=ASGITransport(app=unconfigured), base_url="http://shop.test"
    ) as http:
        body, headers = webhook_body()
        response = await http.post("/api/webhooks/packsenvios", content=body, headers=headers)
        assert response.status_code == 503
    await http.aclose()

    configured = create_app(
        Settings(
            _env_file=None,
            environment="test",
            PACKSENVIOS_WEBHOOK_SECRET=SECRET,
            PACKSENVIOS_WEBHOOK_TIMESTAMP_FORMAT="unix_seconds",
            FREIGHT_COMPANY_ID="00000000-0000-4000-8000-000000000099",
        ),
        engine=db_engine,
    )
    async with AsyncClient(
        transport=ASGITransport(app=configured), base_url="http://shop.test"
    ) as http:
        body, headers = webhook_body(event_id="synthetic-wrong-company")
        response = await http.post("/api/webhooks/packsenvios", content=body, headers=headers)
        assert response.status_code == 403
    await http.aclose()
