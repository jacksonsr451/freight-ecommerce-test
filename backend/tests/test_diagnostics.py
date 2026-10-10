from uuid import UUID, uuid4

import httpx
import testrunner
from _testrunner_support import async_fixture
from domain_fixtures import make_graph
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from freight_ecommerce.config import Settings
from freight_ecommerce.domain import models as m
from freight_ecommerce.freight.client import PacksenviosClient
from freight_ecommerce.freight.config import FreightSettings
from freight_ecommerce.freight.errors import FreightError
from freight_ecommerce.freight.logging import bind_correlation_id
from freight_ecommerce.freight.schemas import QuoteRequest
from freight_ecommerce.freight.synthetic import SyntheticQuoteTransport
from freight_ecommerce.main import create_app

_testrunner_mark = [testrunner.mark.postgres]
TOKEN = "synthetic-diagnostic-bearer-never-log"
EMAIL = "synthetic-diagnostic-buyer@example.invalid"
DOCUMENT = "52998224725"


@async_fixture
async def diagnostic_app(db_engine):
    client = PacksenviosClient(
        FreightSettings(_env_file=None, mode="mock"), transport=SyntheticQuoteTransport()
    )
    app = create_app(
        Settings(_env_file=None, environment="test"), engine=db_engine, freight_client=client
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://diagnostics.test"
    ) as http:
        yield http, db_engine, client, app
    await http.aclose()
    await client.aclose()


async def test_diagnostics_exposes_correlated_safe_fields_and_redacted_snapshot(diagnostic_app):
    http, db, _, _ = diagnostic_app
    correlation = uuid4()
    with Session(db, expire_on_commit=False) as session:
        graph = make_graph(session)
        session.add(
            m.IntegrationAudit(
                correlation_id=correlation,
                checkout_attempt_id=graph.checkout.id,
                quote_id=graph.quote.id,
                operation="quote",
                mode="mock",
                outcome="failed",
                request_key=graph.quote.request_key,
                http_status=429,
                latency_ms=231,
                details={
                    "error_code": "rate_limited",
                    "retry_after_seconds": 19,
                    "packing_mode": "equal_volumes",
                    "external_status": TOKEN,
                    "buyer_email": EMAIL,
                    "document": DOCUMENT,
                    "authorization": f"Bearer {TOKEN}",
                    "snapshot": {
                        "events": [{"buyer_email": EMAIL, "document": DOCUMENT}],
                        "labels": [f"https://labels.invalid/{TOKEN}"],
                    },
                },
            )
        )
        session.commit()
    response = await http.get("/api/diagnostics")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    report = response.json()
    assert report["purchases_simulated"] is True and report["freight_mode"] == "mock"
    checks = {item["name"]: item for item in report["checks"]}
    assert checks["postgresql"]["status"] == "ok"
    assert checks["external_api"]["status"] == "not_checked"
    assert checks["queues"]["status"] == "not_configured"
    operation = next(
        item for item in report["operations"] if item["correlation_id"] == str(correlation)
    )
    assert operation["request_key"] == str(graph.quote.request_key)
    assert operation["quote_id"] == str(graph.quote.id)
    assert operation["external_quote_id"] == str(graph.quote.external_quote_request_id)
    assert operation["latency_ms"] == 231
    assert operation["retry_after_seconds"] == 19
    assert operation["error_code"] == "rate_limited"
    assert operation["redacted_details"]["external_status"] == "[redacted]"
    assert operation["snapshot_summary"] == {
        "redacted": True,
        "field_count": 2,
        "event_count": 1,
        "label_count": 1,
    }
    for secret in (EMAIL, DOCUMENT, TOKEN, "labels.invalid", "authorization"):
        assert secret not in response.text
    assert report["pending_webhook_receipts"] == 1


@testrunner.mark.parametrize("failure", ["network", "timeout"])
async def test_network_and_timeout_logs_are_structured_and_redacted(caplog, failure):
    correlation = str(uuid4())

    async def transport(request: httpx.Request):
        if failure == "network":
            raise httpx.ConnectError(f"private {TOKEN} {EMAIL}", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout(f"private {TOKEN} {EMAIL}", request=request)
        return httpx.Response(
            503,
            json={"message": f"private {TOKEN} {EMAIL} {DOCUMENT}", "body": f"Bearer {TOKEN}"},
        )

    client = PacksenviosClient(
        FreightSettings(
            _env_file=None,
            mode="real",
            base_url="https://freight.synthetic.invalid",
            api_key=TOKEN,
            company_id=UUID("00000000-0000-4000-8000-000000000002"),
            origin_postal_code="01001000",
            integration_scope="synthetic-diagnostics",
            max_attempts=1,
        ),
        transport=httpx.MockTransport(transport),
    )
    request = QuoteRequest(
        request_key=uuid4(),
        destination_postal_code="01001000",
        weight_kg="1.000",
        declared_value_cents=5000,
        length_cm=20,
        width_cm=15,
        height_cm=10,
        volume_count=1,
    )
    try:
        with caplog.at_level("INFO", logger="freight_ecommerce.freight.client"):
            with bind_correlation_id(correlation), testrunner.raises(FreightError):
                await client.create_quote(request)
        records = [
            record
            for record in caplog.records
            if getattr(record, "correlation_id", None) == correlation
        ]
        assert records
        assert any(
            getattr(record, "outcome", None) in {"timeout", "transport_error"} for record in records
        )
        for secret in (TOKEN, EMAIL, DOCUMENT, "private"):
            assert secret not in caplog.text
    finally:
        await client.aclose()


async def test_diagnostics_database_failure_is_normalized_without_connection_details(
    diagnostic_app,
):
    http, _, _, app = diagnostic_app

    class UnavailableEngine:
        def connect(self):
            raise OperationalError(
                "private-database-url", {}, RuntimeError("private-database-password")
            )

    app.state.engine = UnavailableEngine()
    response = await http.get("/api/diagnostics")
    assert response.status_code == 200
    assert any(
        check["name"] == "postgresql" and check["status"] == "unavailable"
        for check in response.json()["checks"]
    )
    assert "private-database-url" not in response.text
    assert "private-database-password" not in response.text
