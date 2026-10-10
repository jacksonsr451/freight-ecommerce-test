from uuid import UUID

import httpx
import testrunner
from _testrunner_support import async_fixture
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from freight_ecommerce.config import Settings
from freight_ecommerce.domain import models as m
from freight_ecommerce.freight.client import PacksenviosClient
from freight_ecommerce.freight.config import FreightSettings
from freight_ecommerce.freight.errors import FreightError
from freight_ecommerce.freight.import_validation import (
    MAX_FILE_BYTES,
    MIME_XLSX,
    ImportFileError,
    validate_import_file,
)
from freight_ecommerce.main import create_app

_testrunner_mark = [testrunner.mark.postgres]
ADMIN_KEY = "synthetic-local-admin-key-for-tests-only"
ADMIN_HEADERS = {"X-Local-Admin-Key": ADMIN_KEY}
COMPANY = UUID("00000000-0000-4000-8000-000000000002")
LOCATION = UUID("00000000-0000-4000-8000-000000000003")
BATCH = UUID("00000000-0000-4000-8000-000000000004")
DISPATCH_CONNECTION = UUID("00000000-0000-4000-8000-000000000005")


def nfe_key():
    base = "3" * 43
    total = sum(int(digit) * (2 + index % 8) for index, digit in enumerate(reversed(base)))
    remainder = total % 11
    check = 0 if remainder in {0, 1} else 11 - remainder
    return base + str(check)


def synthetic_csv(*, valid=True, width=28):
    instruction = "SYNTHETIC FIXTURE — NOT THE OFFICIAL TEMPLATE"
    header = [f"synthetic_fixture_column_{number:02d}" for number in range(1, width + 1)]
    row = [""] * width
    if width == 28:
        values = {
            0: "123",
            1: nfe_key(),
            2: "Destinatário sintético",
            3: "529.982.247-25",
            4: "(11) 98765-4321",
            5: "01001000",
            6: "Rua Sintética",
            7: "1",
            10: "Centro",
            11: "SP",
            12: "1",
            13: "1",
            14: "100,00",
            15: "1,500",
            16: "Remetente sintético",
            17: "11.222.333/0001-81",
            18: "20040002",
            19: "Rua de Origem",
            20: "2",
            23: "Centro",
            24: "RJ",
            25: "10",
            26: "20",
            27: "30",
        }
        for index, value in values.items():
            row[index] = value
        if not valid:
            row[3] = "00000000000"
    import csv
    import io

    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow([instruction])
    writer.writerow(header)
    writer.writerow(row)
    return output.getvalue().encode("utf-8")


def external_summary(status="queued", *, batch_id=BATCH):
    return {
        "id": str(batch_id),
        "filename": "official-orders.csv",
        "status": status,
        "total": 1,
        "valid": 1,
        "invalid": 0,
        "imported": 0,
        "duplicates": 0,
        "processed": 0,
        "issue": None,
        "createdAt": "2026-10-10T12:00:00+00:00",
        "canDelete": False,
        "tmsAvailable": False,
        "dispatch": None,
    }


@async_fixture
async def real_shop(db_engine):
    requests: list[httpx.Request] = []
    remote_status = {
        "value": "review",
        "complete": False,
        "dispatch": None,
        "uncertain_dispatch": False,
        "tracking_refresh_requests": [],
    }

    async def handler(request: httpx.Request):
        requests.append(request)
        path = request.url.path
        if request.method == "POST" and path == "/api/v1/freight/order-imports":
            return httpx.Response(202, json=external_summary("queued"))
        if request.method == "GET" and path == f"/api/v1/freight/order-imports/{BATCH}":
            status = remote_status["value"]
            complete = remote_status["complete"]
            payload = {
                **external_summary(status),
                "valid": 1 if complete else 1,
                "invalid": 0 if complete else 1,
                "total": 1 if complete else 2,
                "imported": 1 if complete else 0,
                "processed": 1 if complete else 0,
                "dispatch": remote_status["dispatch"],
                "items": [
                    {
                        "row": 37,
                        "status": "synthetic_imported" if complete else "invalid",
                        "invoiceNumber": "123",
                        "recipientName": "Destinatário sintético",
                        "destination": "01001000",
                        "volumes": 1,
                        "weightKg": "1.500",
                        "errors": ["synthetic_validation_issue"],
                        "shipmentId": "synthetic-shipment-id" if complete else None,
                        "publicCode": None,
                        "dispatchStatus": None,
                    }
                ],
                "hasMore": False,
                "nextCursor": None,
            }
            return httpx.Response(200, json=payload)
        if request.method == "POST" and path == f"/api/v1/freight/order-imports/{BATCH}/confirm":
            remote_status["value"] = "confirming"
            return httpx.Response(202, json=external_summary("confirming"))
        if request.method == "POST" and path == f"/api/v1/freight/order-imports/{BATCH}/dispatch":
            body = request.content
            assert str(DISPATCH_CONNECTION).encode() in body
            assert b'"confirm_dispatch":true' in body
            uncertain = 1 if remote_status["uncertain_dispatch"] else 0
            result = {
                "id": "synthetic-dispatch-request-001",
                "batchId": str(BATCH),
                "connectionId": str(DISPATCH_CONNECTION),
                "status": "queued",
                "total": 1,
                "enqueued": 1,
                "accepted": 0,
                "rejected": 0,
                "uncertain": uncertain,
                "issue": None,
            }
            if not remote_status["uncertain_dispatch"]:
                remote_status["dispatch"] = result
            return httpx.Response(202, json=result)
        if request.method == "GET" and path.endswith("/rows/37/tracking"):
            return httpx.Response(
                200,
                json={
                    "code": "synthetic-public-code",
                    "reference": "synthetic-reference",
                    "acceptedAt": "2026-10-10T12:00:00+00:00",
                    "updatedAt": "2026-10-10T13:00:00+00:00",
                    "issue": None,
                    "labels": [],
                    "labelsAt": None,
                    "events": [
                        {"synthetic_fixture_order": 2, "event": "later"},
                        {"synthetic_fixture_order": 1, "event": "earlier"},
                    ],
                },
            )
        if request.method == "POST" and "/rows/37/tracking" in path:
            remote_status["tracking_refresh_requests"].append(request)
            return httpx.Response(202, json={"status": "queued"})
        return httpx.Response(404, json={"message": "synthetic not found"})

    settings = FreightSettings(
        _env_file=None,
        mode="real",
        base_url="https://freight.synthetic.invalid",
        api_key="synthetic-import-bearer-token-only-for-mock-transport",
        company_id=COMPANY,
        location_id=LOCATION,
        dispatch_connection_id=DISPATCH_CONNECTION,
        integration_scope="synthetic-import-tests",
        max_attempts=3,
    )
    client = PacksenviosClient(settings, transport=httpx.MockTransport(handler))
    app = create_app(
        Settings(_env_file=None, environment="test", LOCAL_ADMIN_KEY=ADMIN_KEY),
        engine=db_engine,
        freight_client=client,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://shop.test") as http:
        yield http, db_engine, requests, remote_status, client
    await http.aclose()
    await client.aclose()


async def test_upload_batch_persists_deduplicates_reads_errors_and_explicitly_confirms(real_shop):
    http, db, requests, remote_status, _ = real_shop
    file = synthetic_csv()
    first = await http.post(
        "/api/admin/imports",
        headers=ADMIN_HEADERS,
        files={"file": ("official-orders.csv", file, "text/csv")},
    )
    assert first.status_code == 202, first.text
    batch = first.json()
    assert batch["id"] == str(BATCH) and batch["external_status"] == "queued"
    assert batch["local_status"] == "upload_pending"
    replay = await http.post(
        "/api/admin/imports",
        headers=ADMIN_HEADERS,
        files={"file": ("official-orders.csv", file, "text/csv")},
    )
    assert replay.status_code == 202 and replay.json() == batch
    upload_requests = [
        request for request in requests if request.url.path.endswith("/order-imports")
    ]
    assert len(upload_requests) == 1
    assert upload_requests[0].headers["authorization"].startswith("Bearer ")
    assert b"freight_company_id" in upload_requests[0].content
    assert str(COMPANY).encode() in upload_requests[0].content
    assert str(LOCATION).encode() in upload_requests[0].content

    detail = await http.get(
        f"/api/admin/imports/{BATCH}?cursor=0&errors_only=true", headers=ADMIN_HEADERS
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["external_status"] == "review"
    assert detail.json()["items"][0]["errors"] == ["synthetic_validation_issue"]
    query = next(request for request in requests if request.method == "GET")
    assert query.url.params["cursor"] == "0" and query.url.params["errors_only"] == "1"
    later_page = await http.get(
        f"/api/admin/imports/{BATCH}?cursor=50&errors_only=true", headers=ADMIN_HEADERS
    )
    assert later_page.status_code == 200
    cursor_request = [request for request in requests if request.method == "GET"][-1]
    assert cursor_request.url.params["cursor"] == "50"
    assert cursor_request.url.params["errors_only"] == "1"

    no_review = await http.post(
        f"/api/admin/imports/{BATCH}/confirm",
        headers=ADMIN_HEADERS,
        json={"confirm_valid_rows": True, "operator_reviewed": False},
    )
    assert no_review.status_code == 422
    confirmed = await http.post(
        f"/api/admin/imports/{BATCH}/confirm",
        headers=ADMIN_HEADERS,
        json={"confirm_valid_rows": True, "operator_reviewed": True},
    )
    assert confirmed.status_code == 202, confirmed.text
    assert confirmed.json()["external_status"] == "confirming"
    confirm_request = next(
        request
        for request in requests
        if request.method == "POST" and request.url.path.endswith("/confirm")
    )
    assert confirm_request.url.params["freight_company_id"] == str(COMPANY)
    assert confirm_request.url.params["freight_location_id"] == str(LOCATION)
    assert b'"confirm_valid_rows":true' in confirm_request.content
    with Session(db) as session:
        stored = session.scalar(select(m.ShipmentImportBatch))
        assert stored.external_batch_id == BATCH
        assert stored.status.value == "confirmation_pending"
        assert (
            session.scalar(
                select(func.count())
                .select_from(m.IntegrationAudit)
                .where(m.IntegrationAudit.operation == "order_import_uploaded")
            )
            == 1
        )


async def test_confirmation_waits_for_validation_and_external_429_is_not_retried(real_shop):
    http, _, requests, remote_status, _ = real_shop
    uploaded = await http.post(
        "/api/admin/imports",
        headers=ADMIN_HEADERS,
        files={"file": ("official-orders.csv", synthetic_csv(), "text/csv")},
    )
    assert uploaded.status_code == 202
    remote_status["value"] = "parsing"
    blocked = await http.post(
        f"/api/admin/imports/{BATCH}/confirm",
        headers=ADMIN_HEADERS,
        json={"confirm_valid_rows": True, "operator_reviewed": True},
    )
    assert blocked.status_code == 409
    assert not any(request.url.path.endswith("/confirm") for request in requests)
    throttled_requests = []

    async def throttled(request: httpx.Request):
        throttled_requests.append(request)
        return httpx.Response(429, headers={"Retry-After": "17"}, json={"message": "throttled"})

    throttled_client = PacksenviosClient(
        FreightSettings(
            _env_file=None,
            mode="real",
            base_url="https://freight.synthetic.invalid",
            api_key="synthetic-import-bearer-token-only-for-mock-transport",
            company_id=COMPANY,
            integration_scope="synthetic-throttle-test",
            max_attempts=3,
        ),
        transport=httpx.MockTransport(throttled),
    )
    try:
        with testrunner.raises(FreightError) as error:
            await throttled_client.upload_order_import(
                "official-orders.csv", synthetic_csv(), "text/csv"
            )
        assert getattr(error.value, "http_status", None) == 429
        assert getattr(error.value, "retry_after_seconds", None) == 17
        assert len(throttled_requests) == 1
    finally:
        await throttled_client.aclose()


async def test_invalid_csv_mode_and_export_readiness_never_call_external(real_shop):
    http, _, requests, _, _ = real_shop
    invalid = await http.post(
        "/api/admin/imports",
        headers=ADMIN_HEADERS,
        files={"file": ("bad.csv", synthetic_csv(width=27), "text/csv")},
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "file_header_width_invalid"
    readiness = await http.get("/api/admin/imports/export-readiness", headers=ADMIN_HEADERS)
    assert readiness.status_code == 200 and readiness.json()["can_export"] is False
    assert any("nfe_access_key" in item for item in readiness.json()["missing_fields"])
    assert requests == []


def test_csv_fiscal_validation_xlsx_structure_and_file_size_caps():
    with testrunner.raises(ImportFileError, match="CPF/CNPJ inválido"):
        validate_import_file("synthetic.csv", "text/csv", synthetic_csv(valid=False))
    with testrunner.raises(ImportFileError, match="acima do limite"):
        validate_import_file("synthetic.csv", "text/csv", b"x" * (MAX_FILE_BYTES + 1))
    with testrunner.raises(ImportFileError, match="XLSX inválido"):
        validate_import_file("synthetic.xlsx", MIME_XLSX, b"not a zip workbook")


async def test_mock_mode_upload_is_disabled_and_local_admin_protects_gateway(db_engine):
    from freight_ecommerce.freight.synthetic import SyntheticQuoteTransport

    client = PacksenviosClient(
        FreightSettings(_env_file=None, mode="mock"),
        transport=SyntheticQuoteTransport(),
    )
    app = create_app(
        Settings(_env_file=None, environment="test", LOCAL_ADMIN_KEY=ADMIN_KEY),
        engine=db_engine,
        freight_client=client,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://shop.test") as http:
        unauthorized = await http.get("/api/admin/imports/availability")
        assert unauthorized.status_code == 401
        availability = await http.get("/api/admin/imports/availability", headers=ADMIN_HEADERS)
        assert availability.status_code == 200 and availability.json()["upload_enabled"] is False
        denied = await http.post(
            "/api/admin/imports",
            headers=ADMIN_HEADERS,
            files={"file": ("synthetic.csv", synthetic_csv(), "text/csv")},
        )
        assert denied.status_code == 409
        assert denied.json()["detail"]["code"] == "import_real_mode_required"
    await http.aclose()
    await client.aclose()


async def test_external_ability_denial_is_normalized_and_not_retried(db_engine):
    received = []

    async def forbidden(request: httpx.Request):
        received.append(request)
        return httpx.Response(403, json={"message": "synthetic private response"})

    token = "synthetic-import-bearer-token-only-for-mock-transport"
    client = PacksenviosClient(
        FreightSettings(
            _env_file=None,
            mode="real",
            base_url="https://freight.synthetic.invalid",
            api_key=token,
            company_id=COMPANY,
            integration_scope="synthetic-forbidden-test",
            max_attempts=3,
        ),
        transport=httpx.MockTransport(forbidden),
    )
    app = create_app(
        Settings(_env_file=None, environment="test", LOCAL_ADMIN_KEY=ADMIN_KEY),
        engine=db_engine,
        freight_client=client,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://shop.test") as http:
        denied = await http.post(
            "/api/admin/imports",
            headers=ADMIN_HEADERS,
            files={"file": ("synthetic.csv", synthetic_csv(), "text/csv")},
        )
        assert denied.status_code == 403
        assert "synthetic private response" not in denied.text
        assert token not in denied.text
        assert len(received) == 1
    await http.aclose()
    await client.aclose()


async def test_dispatch_requires_existing_connection_and_complete_import(real_shop):
    http, _, requests, remote_status, _ = real_shop
    uploaded = await http.post(
        "/api/admin/imports",
        headers=ADMIN_HEADERS,
        files={"file": ("official-orders.csv", synthetic_csv(), "text/csv")},
    )
    assert uploaded.status_code == 202
    remote_status["value"] = "imported"
    remote_status["complete"] = False
    blocked = await http.post(
        f"/api/admin/imports/{BATCH}/dispatch",
        headers=ADMIN_HEADERS,
        json={"confirm_dispatch": True, "operator_confirmed": True},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "import_dispatch_not_ready"
    assert not any(request.url.path.endswith("/dispatch") for request in requests)


async def test_dispatch_202_stays_pending_and_existing_request_is_never_reposted(real_shop):
    http, db, requests, remote_status, _ = real_shop
    uploaded = await http.post(
        "/api/admin/imports",
        headers=ADMIN_HEADERS,
        files={"file": ("official-orders.csv", synthetic_csv(), "text/csv")},
    )
    assert uploaded.status_code == 202
    remote_status["value"] = "imported"
    remote_status["complete"] = True
    path = f"/api/admin/imports/{BATCH}/dispatch"
    body = {"confirm_dispatch": True, "operator_confirmed": True}
    first = await http.post(path, headers=ADMIN_HEADERS, json=body)
    assert first.status_code == 202, first.text
    result = first.json()
    assert result["batch"]["local_status"] == "dispatch_pending"
    assert result["batch"]["external_status"] == "imported"
    assert result["batch"]["dispatch_status"] == "queued"
    assert result["dispatch"]["enqueued"] == 1
    assert result["dispatch"]["accepted"] == 0
    assert result["dispatch_retry_blocked"] is True
    assert result["reconciliation_required"] is False
    dispatch_calls = [request for request in requests if request.url.path.endswith("/dispatch")]
    assert len(dispatch_calls) == 1
    assert dispatch_calls[0].url.params["freight_company_id"] == str(COMPANY)
    assert dispatch_calls[0].url.params["freight_location_id"] == str(LOCATION)

    reconciled = await http.post(path, headers=ADMIN_HEADERS, json=body)
    assert reconciled.status_code == 202
    assert reconciled.json()["dispatch"]["id"] == "synthetic-dispatch-request-001"
    assert len([request for request in requests if request.url.path.endswith("/dispatch")]) == 1
    with Session(db) as session:
        batch = session.scalar(select(m.ShipmentImportBatch))
        assert batch.status.value == "dispatch_pending"
        assert batch.external_status == "imported"
        assert batch.external_dispatch_request_id == "synthetic-dispatch-request-001"
        assert batch.external_dispatch_status == "queued"


async def test_uncertain_dispatch_is_reconciled_without_a_blind_retry(real_shop):
    http, db, requests, remote_status, _ = real_shop
    uploaded = await http.post(
        "/api/admin/imports",
        headers=ADMIN_HEADERS,
        files={"file": ("official-orders.csv", synthetic_csv(), "text/csv")},
    )
    assert uploaded.status_code == 202
    remote_status["value"] = "imported"
    remote_status["complete"] = True
    remote_status["uncertain_dispatch"] = True
    path = f"/api/admin/imports/{BATCH}/dispatch"
    body = {"confirm_dispatch": True, "operator_confirmed": True}
    result = await http.post(path, headers=ADMIN_HEADERS, json=body)
    assert result.status_code == 202
    assert result.json()["dispatch"]["uncertain"] == 1
    assert result.json()["reconciliation_required"] is True
    replay = await http.post(path, headers=ADMIN_HEADERS, json=body)
    assert replay.status_code == 202
    assert replay.json()["dispatch_retry_blocked"] is True
    assert replay.json()["reconciliation_required"] is True
    assert len([request for request in requests if request.url.path.endswith("/dispatch")]) == 1
    with Session(db) as session:
        audit = session.scalar(
            select(m.IntegrationAudit)
            .where(m.IntegrationAudit.operation == "order_import_dispatch")
            .order_by(m.IntegrationAudit.created_at.desc())
        )
        assert audit.outcome == "uncertain"


async def test_tracking_uses_spreadsheet_row_keeps_real_snapshot_order_and_throttles_refresh(
    real_shop,
):
    http, db, requests, remote_status, _ = real_shop
    uploaded = await http.post(
        "/api/admin/imports",
        headers=ADMIN_HEADERS,
        files={"file": ("official-orders.csv", synthetic_csv(), "text/csv")},
    )
    assert uploaded.status_code == 202
    snapshot = await http.get(f"/api/admin/imports/{BATCH}/rows/37/tracking", headers=ADMIN_HEADERS)
    assert snapshot.status_code == 200
    assert snapshot.headers["cache-control"] == "private, no-store"
    tracking = snapshot.json()
    assert tracking["source"] == "packsenvios"
    assert tracking["row_number"] == 37
    assert tracking["snapshot"]["labels"] == []
    assert [event["synthetic_fixture_order"] for event in tracking["snapshot"]["events"]] == [2, 1]
    external_get = next(
        request
        for request in requests
        if request.method == "GET" and "/tracking" in request.url.path
    )
    assert external_get.url.path.endswith(f"/order-imports/{BATCH}/rows/37/tracking")
    assert external_get.url.params["freight_company_id"] == str(COMPANY)

    queued = await http.post(f"/api/admin/imports/{BATCH}/rows/37/tracking", headers=ADMIN_HEADERS)
    assert queued.status_code == 202
    assert queued.json() == {
        "batch_id": str(BATCH),
        "row_number": 37,
        "source": "packsenvios",
        "status": "queued",
    }
    throttled = await http.post(
        f"/api/admin/imports/{BATCH}/rows/37/tracking", headers=ADMIN_HEADERS
    )
    assert throttled.status_code == 429
    assert 1 <= int(throttled.headers["Retry-After"]) <= 60
    assert len(remote_status["tracking_refresh_requests"]) == 1
    invalid_row = await http.get(
        f"/api/admin/imports/{BATCH}/rows/2/tracking", headers=ADMIN_HEADERS
    )
    assert invalid_row.status_code == 422

    detail = await http.get(f"/api/admin/imports/{BATCH}?cursor=0", headers=ADMIN_HEADERS)
    assert detail.status_code == 200
    tracking_activity = [
        item
        for item in detail.json()["activity"]
        if item["operation"] == "order_import_tracking_snapshot"
    ]
    assert tracking_activity[-1]["details"]["source"] == "packsenvios"
    assert [
        event["synthetic_fixture_order"]
        for event in tracking_activity[-1]["details"]["snapshot"]["events"]
    ] == [2, 1]
    with Session(db) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(m.IntegrationAudit)
                .where(m.IntegrationAudit.operation == "order_import_tracking_refresh")
            )
            == 1
        )


async def test_missing_dispatch_connection_blocks_without_posting(db_engine):
    requests = []

    async def handler(request: httpx.Request):
        requests.append(request)
        if request.method == "POST" and request.url.path.endswith("/order-imports"):
            return httpx.Response(202, json=external_summary("queued"))
        if request.method == "GET" and request.url.path.endswith(f"/order-imports/{BATCH}"):
            return httpx.Response(
                200,
                json={
                    **external_summary("imported"),
                    "total": 1,
                    "processed": 1,
                    "imported": 1,
                    "invalid": 0,
                    "dispatch": None,
                    "items": [],
                    "hasMore": False,
                    "nextCursor": None,
                },
            )
        return httpx.Response(404)

    client = PacksenviosClient(
        FreightSettings(
            _env_file=None,
            mode="real",
            base_url="https://freight.synthetic.invalid",
            api_key="synthetic-import-bearer-token-only-for-mock-transport",
            company_id=COMPANY,
            integration_scope="synthetic-no-dispatch-connection",
        ),
        transport=httpx.MockTransport(handler),
    )
    app = create_app(
        Settings(_env_file=None, environment="test", LOCAL_ADMIN_KEY=ADMIN_KEY),
        engine=db_engine,
        freight_client=client,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://shop.test") as http:
        uploaded = await http.post(
            "/api/admin/imports",
            headers=ADMIN_HEADERS,
            files={"file": ("official-orders.csv", synthetic_csv(), "text/csv")},
        )
        assert uploaded.status_code == 202
        denied = await http.post(
            f"/api/admin/imports/{BATCH}/dispatch",
            headers=ADMIN_HEADERS,
            json={"confirm_dispatch": True, "operator_confirmed": True},
        )
        assert denied.status_code == 409
        assert denied.json()["detail"]["code"] == "dispatch_connection_not_configured"
        assert not any(request.url.path.endswith("/dispatch") for request in requests)
    await http.aclose()
    await client.aclose()
