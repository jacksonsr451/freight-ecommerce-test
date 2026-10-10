import asyncio
import json
from copy import deepcopy
from datetime import timedelta
from uuid import UUID

import httpx
import testrunner
from _testrunner_support import async_fixture
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from freight_ecommerce.catalog.seed import seed_demo_catalog
from freight_ecommerce.config import Settings
from freight_ecommerce.database import transaction
from freight_ecommerce.domain import models as m
from freight_ecommerce.domain.base import utcnow
from freight_ecommerce.domain.states import QuoteStatus
from freight_ecommerce.freight.client import PacksenviosClient
from freight_ecommerce.freight.config import FreightSettings
from freight_ecommerce.freight.synthetic import SYNTHETIC_COMPANY_ID, SyntheticQuoteTransport
from freight_ecommerce.main import create_app

_testrunner_mark = [testrunner.mark.postgres]
ADDRESS = {
    "postal_code": "01001000",
    "street": "Rua sintética",
    "number": "1",
    "district": "Centro",
    "city": "São Paulo",
    "state": "SP",
    "country": "BR",
}


@async_fixture
async def harness(db_engine):
    with transaction(db_engine) as session:
        seed_demo_catalog(session)
    clients = []

    def make(handler=None, scenario="quoted", **settings):
        provider = SyntheticQuoteTransport(scenario)
        observed = []

        async def transport(request):
            observed.append(request)
            if handler is not None:
                return await handler(request, provider)
            return await provider.handle_async_request(request)

        client = PacksenviosClient(
            FreightSettings(
                _env_file=None,
                **{
                    "mode": "mock",
                    "company_id": SYNTHETIC_COMPANY_ID,
                    "location_id": None,
                    "origin_postal_code": "01001000",
                    "max_attempts": 1,
                    "integration_scope": "synthetic-engine-test",
                    **settings,
                },
            ),
            transport=httpx.MockTransport(transport),
        )
        app = create_app(
            Settings(_env_file=None, environment="test"), engine=db_engine, freight_client=client
        )
        http = AsyncClient(transport=ASGITransport(app=app), base_url="http://local.test")
        clients.append((http, client))
        return http, observed, provider, app

    try:
        yield make
    finally:
        for http, client in clients:
            await http.aclose()
            await client.aclose()


@async_fixture
async def prepared(harness, db_engine):
    http, calls, provider, app = harness()
    cart = await make_cart(http, db_engine)
    yield http, calls, provider, app, cart
    await http.aclose()
    await app.state.freight_client.aclose()


async def make_cart(http, engine, sku="DEMO-BOOK", quantity=1):
    cart = (await http.post("/api/carts", json={})).json()
    with Session(engine) as session:
        product = session.scalar(select(m.Product.id).where(m.Product.sku == sku))
    cart = (
        await http.post(
            f"/api/carts/{cart['id']}/items",
            json={
                "expected_revision": cart["revision"],
                "product_id": str(product),
                "quantity": quantity,
            },
        )
    ).json()
    cart = (
        await http.put(
            f"/api/carts/{cart['id']}/address",
            json={
                "expected_revision": cart["revision"],
                "address": ADDRESS,
            },
        )
    ).json()
    return cart


async def quote(http, cart, **fields):
    return await http.post(
        f"/api/carts/{cart['id']}/freight-quotes",
        json={
            "expected_revision": cart["revision"],
            **fields,
        },
    )


def record(engine, reference):
    with Session(engine) as session:
        row = session.get(m.FreightQuote, UUID(reference))
        return {
            "key": row.request_key,
            "id": row.external_quote_request_id,
            "payload": row.prepared_payload,
            "response": deepcopy(row.response),
            "criteria": deepcopy(row.criteria),
            "status": row.status,
        }


async def test_equal_volumes_derived_from_catalog_and_committed_before_http(harness, db_engine):
    async def handler(request, provider):
        body = json.loads(request.content)
        with Session(db_engine) as session:
            saved = session.scalar(
                select(m.FreightQuote).where(
                    m.FreightQuote.request_key == UUID(body["request_key"])
                )
            )
            assert saved is not None and saved.prepared_payload == request.content
            assert saved.cart_id is not None and saved.checkout_attempt_id is None
            assert session.scalar(select(func.count()).select_from(m.Customer)) == 0
        assert body["weight_kg"] == "0.900" and body["declared_value_cents"] == 9180
        assert body["length_cm"] == 23 and body["width_cm"] == 16 and body["height_cm"] == 3
        assert body["volume_count"] == len(body["volumes"]) == 2
        assert sum(item["weight_grams"] for item in body["volumes"]) == 900
        return await provider.handle_async_request(request)

    http, calls, _, app = harness(handler)
    try:
        cart = await make_cart(http, db_engine, quantity=2)
        response = await quote(http, cart)
        assert response.status_code == 200
        view = response.json()
        assert view["status"] == "quoted" and len(view["options"]) == 1
        assert view["options"][0]["manual_only"] is True
        assert view["options"][0]["manual_review_required"] is True
        saved = record(db_engine, view["quote_reference"])
        assert (
            saved["status"] == QuoteStatus.RECEIVED
            and saved["response"]["data"]["status"] == "quoted"
        )
        assert saved["key"] != saved["id"] and saved["payload"] == calls[0].content
        assert "criteria" not in view and "request_key" not in view
        assert "calculation_snapshot" not in view["options"][0]
    finally:
        await http.aclose()
        await app.state.freight_client.aclose()


async def test_replay_uses_persisted_response_without_http_or_snapshot_duplication(
    prepared, db_engine
):
    http, calls, _, _, cart = prepared
    first = (await quote(http, cart)).json()
    before = record(db_engine, first["quote_reference"])
    replay = (await quote(http, cart)).json()
    assert replay == first and len(calls) == 1
    assert record(db_engine, first["quote_reference"]) == before
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(m.FreightOptionSnapshot)) == 1
    read = await http.get(f"/api/carts/{cart['id']}/freight-quotes/{first['quote_reference']}")
    assert read.json() == first and len(calls) == 1


@testrunner.mark.parametrize("scenario", ["unavailable", "fiscal_review"])
async def test_no_offer_states_are_persisted_without_price_zero(harness, db_engine, scenario):
    http, calls, _, app = harness(scenario=scenario)
    try:
        cart = await make_cart(http, db_engine)
        result = (await quote(http, cart)).json()
        assert result["status"] == scenario and result["options"] == []
        saved = record(db_engine, result["quote_reference"])
        assert saved["response"]["data"]["options"] == []
        assert (await quote(http, cart)).json() == result and len(calls) == 1
    finally:
        await http.aclose()
        await app.state.freight_client.aclose()


async def test_divergent_geometry_requires_explicit_weight_only_and_cannot_select(
    prepared, db_engine
):
    http, calls, _, _, cart = prepared
    with Session(db_engine) as session:
        mug = session.scalar(select(m.Product.id).where(m.Product.sku == "DEMO-MUG"))
    cart = (
        await http.post(
            f"/api/carts/{cart['id']}/items",
            json={
                "expected_revision": cart["revision"],
                "product_id": str(mug),
                "quantity": 1,
            },
        )
    ).json()
    invalid = await quote(http, cart)
    assert invalid.status_code == 422 and invalid.json()["detail"]["code"] == "unequal_volumes"
    assert calls == []
    estimate = (await quote(http, cart, packing_mode="weight_only")).json()
    assert estimate["weight_only"] and estimate["options"][0]["weight_only"]
    payload = json.loads(calls[0].content)
    assert payload["weight_kg"] == "0.810" and payload["declared_value_cents"] == 8080
    assert not {"length_cm", "volume_count", "volumes"} & payload.keys()
    rejected = await http.post(
        f"/api/carts/{cart['id']}/freight-quotes/{estimate['quote_reference']}/selection",
        json={
            "expected_revision": cart["revision"],
            "option_reference": estimate["options"][0]["reference"],
        },
    )
    assert (
        rejected.status_code == 409
        and rejected.json()["detail"]["code"] == "estimate_not_selectable"
    )


async def test_multiple_options_same_table_have_distinct_refs_and_selection_is_only_local(
    harness, db_engine
):
    async def handler(request, provider):
        response = await provider.handle_async_request(request)
        body = response.json()
        second = deepcopy(body["data"]["options"][0])
        second["price_cents"] = 3500
        second["deadline_days"] = 1
        body["data"]["options"].append(second)
        return httpx.Response(200, json=body)

    http, calls, _, app = harness(handler)
    try:
        cart = await make_cart(http, db_engine)
        result = (await quote(http, cart)).json()
        assert len({option["reference"] for option in result["options"]}) == 2
        selected = await http.post(
            f"/api/carts/{cart['id']}/freight-quotes/{result['quote_reference']}/selection",
            json={
                "expected_revision": cart["revision"],
                "option_reference": result["options"][1]["reference"],
            },
        )
        assert selected.status_code == 200
        assert selected.json()["selected_option_reference"] == result["options"][1]["reference"]
        assert len(calls) == 1 and all(
            request.url.path == "/api/v1/freight/quotes" for request in calls
        )
        with Session(db_engine) as session:
            assert session.scalar(select(func.count()).select_from(m.Order)) == 0
            assert session.scalar(select(func.count()).select_from(m.PaymentSimulation)) == 0
            assert all(stock.reserved == 0 for stock in session.scalars(select(m.Inventory)))
    finally:
        await http.aclose()
        await app.state.freight_client.aclose()


async def test_timeout_after_provider_persistence_keeps_key_and_replays_exact_bytes(
    harness, db_engine
):
    async def handler(request, provider):
        response = await provider.handle_async_request(request)
        if len(provider.by_key) == 1 and not getattr(provider, "lost_once", False):
            provider.lost_once = True
            raise httpx.ReadTimeout("synthetic lost response", request=request)
        return response

    http, calls, _, app = harness(handler)
    try:
        cart = await make_cart(http, db_engine)
        assert (await quote(http, cart)).status_code == 504
        with Session(db_engine) as session:
            row = session.scalar(select(m.FreightQuote))
            key, raw = row.request_key, row.prepared_payload
            assert row.status == QuoteStatus.REQUESTED and row.response is None
            assert row.inflight_token is None and row.last_error_code == "timeout"
        response = await quote(http, cart)
        assert response.status_code == 200
        saved = record(db_engine, response.json()["quote_reference"])
        assert saved["key"] == key and calls[0].content == calls[1].content == raw
        with Session(db_engine) as session:
            assert session.scalar(select(func.count()).select_from(m.FreightQuote)) == 1
    finally:
        await http.aclose()
        await app.state.freight_client.aclose()


async def test_change_criteria_and_explicit_refresh_generate_new_keys_preserving_old_snapshots(
    prepared, db_engine
):
    http, _, _, _, cart = prepared
    first = (await quote(http, cart)).json()
    old = record(db_engine, first["quote_reference"])
    cart = (
        await http.patch(
            f"/api/carts/{cart['id']}/items/{cart['items'][0]['id']}",
            json={
                "expected_revision": cart["revision"],
                "quantity": 2,
            },
        )
    ).json()
    second = (await quote(http, cart)).json()
    new = record(db_engine, second["quote_reference"])
    assert new["key"] != old["key"] and new["criteria"]["weight_kg"] == "0.900"
    before = record(db_engine, first["quote_reference"])
    assert before["status"] == QuoteStatus.INVALIDATED and before["response"] == old["response"]
    refreshed = (await quote(http, cart, refresh=True)).json()
    assert record(db_engine, refreshed["quote_reference"])["key"] != new["key"]


async def test_two_concurrent_requests_share_pending_reference_and_one_http(harness, db_engine):
    started, release = asyncio.Event(), asyncio.Event()

    async def handler(request, provider):
        started.set()
        await release.wait()
        return await provider.handle_async_request(request)

    http, calls, _, app = harness(handler)
    try:
        cart = await make_cart(http, db_engine)
        task = asyncio.create_task(quote(http, cart))
        await asyncio.wait_for(started.wait(), 5)
        duplicate = await quote(http, cart)
        assert duplicate.status_code == 202 and duplicate.json()["status"] == "pending"
        release.set()
        completed = await task
        assert completed.status_code == 200
        assert duplicate.json()["quote_reference"] == completed.json()["quote_reference"]
        assert len(calls) == 1
    finally:
        release.set()
        await http.aclose()
        await app.state.freight_client.aclose()


async def test_late_response_cannot_revive_a_quote_after_cart_change(harness, db_engine):
    started, release = asyncio.Event(), asyncio.Event()

    async def handler(request, provider):
        started.set()
        await release.wait()
        return await provider.handle_async_request(request)

    http, calls, _, app = harness(handler)
    try:
        cart = await make_cart(http, db_engine)
        task = asyncio.create_task(quote(http, cart))
        await asyncio.wait_for(started.wait(), 5)
        changed = await http.patch(
            f"/api/carts/{cart['id']}/items/{cart['items'][0]['id']}",
            json={
                "expected_revision": cart["revision"],
                "quantity": 2,
            },
        )
        assert changed.status_code == 200  # cart lock is not held across HTTP
        release.set()
        response = await task
        assert (
            response.status_code == 409
            and response.json()["detail"]["code"] == "quote_criteria_changed"
        )
        with Session(db_engine) as session:
            row = session.scalar(select(m.FreightQuote))
            assert row.status == QuoteStatus.INVALIDATED and row.response is not None
            assert row.external_status == "quoted"
            assert session.scalar(select(func.count()).select_from(m.FreightOptionSnapshot)) == 1
        assert len(calls) == 1
    finally:
        release.set()
        await http.aclose()
        await app.state.freight_client.aclose()


async def test_unknown_optional_flags_and_secret_echo_are_not_fabricated_or_published(
    harness, db_engine
):
    key = "synthetic-engine-secret-never-browser"

    async def handler(request, provider):
        response = await provider.handle_async_request(request)
        body = response.json()
        option = body["data"]["options"][0]
        option.pop("manual_only")
        option.pop("demonstration_only")
        option["carrier_name"] = f"Bearer {key}"
        body["private_debug"] = key
        return httpx.Response(200, json=body)

    http, _, _, app = harness(handler, api_key=key)
    try:
        cart = await make_cart(http, db_engine)
        response = await quote(http, cart)
        assert response.status_code == 200 and key not in response.text
        offer = response.json()["options"][0]
        assert offer["manual_only"] is None and offer["demonstration_only"] is None
        assert offer["carrier_name"] is None and offer["manual_review_required"]
        with Session(db_engine) as session:
            snapshot = session.scalar(select(m.FreightOptionSnapshot))
            assert snapshot.manual_only is None and snapshot.demonstration_only is None
            assert snapshot.payload["carrier_name"] == f"Bearer {key}"
    finally:
        await http.aclose()
        await app.state.freight_client.aclose()


@testrunner.mark.parametrize(
    "field", ["weight_kg", "declared_value_cents", "length_cm", "freight_company_id"]
)
async def test_browser_cannot_override_commercial_or_context_criteria(prepared, field):
    http, calls, _, _, cart = prepared
    response = await quote(http, cart, **{field: 1})
    assert response.status_code == 422 and calls == []


async def test_option_from_other_cart_or_arbitrary_price_is_rejected(prepared, db_engine):
    http, _, _, _, cart = prepared
    first = (await quote(http, cart)).json()
    other = await make_cart(http, db_engine)
    second = (await quote(http, other)).json()
    path = f"/api/carts/{cart['id']}/freight-quotes/{first['quote_reference']}/selection"
    rejected = await http.post(
        path,
        json={
            "expected_revision": cart["revision"],
            "option_reference": second["options"][0]["reference"],
        },
    )
    assert rejected.status_code == 404
    forged = await http.post(
        path,
        json={
            "expected_revision": cart["revision"],
            "option_reference": first["options"][0]["reference"],
            "price_cents": 1,
        },
    )
    assert forged.status_code == 422
    assert (
        await http.get(f"/api/carts/{other['id']}/freight-quotes/{first['quote_reference']}")
    ).status_code == 404


async def test_reply_transaction_failure_does_not_lose_durable_request(harness, db_engine):
    http, calls, _, app = harness()
    cart = await make_cart(http, db_engine)

    def fail_snapshot(mapper, connection, target):
        raise IntegrityError("synthetic", {}, RuntimeError("synthetic persistence failure"))

    event.listen(m.FreightOptionSnapshot, "before_insert", fail_snapshot)
    try:
        response = await quote(http, cart)
        assert response.status_code == 409
    finally:
        event.remove(m.FreightOptionSnapshot, "before_insert", fail_snapshot)
    with transaction(db_engine) as session:
        row = session.scalar(select(m.FreightQuote))
        assert row.prepared_payload == calls[0].content and row.response is None
        row.inflight_until = utcnow() - timedelta(
            seconds=1
        )  # recovery after the owned lease expires
    try:
        retry = await quote(http, cart)
        assert retry.status_code == 200 and calls[0].content == calls[1].content
    finally:
        await http.aclose()
        await app.state.freight_client.aclose()


@testrunner.mark.parametrize("status", [429, 503])
async def test_retry_after_blocks_early_refresh_and_changed_criteria(harness, db_engine, status):
    async def handler(request, provider):
        return httpx.Response(status, headers={"Retry-After": "60"}, json={"message": "synthetic"})

    http, calls, _, app = harness(handler)
    try:
        cart = await make_cart(http, db_engine)
        first = await quote(http, cart)
        assert first.status_code == status and first.headers["Retry-After"] == "60"
        early = await quote(http, cart, refresh=True)
        assert early.status_code == 429 and "Retry-After" in early.headers and len(calls) == 1
        cart = (
            await http.patch(
                f"/api/carts/{cart['id']}/items/{cart['items'][0]['id']}",
                json={
                    "expected_revision": cart["revision"],
                    "quantity": 2,
                },
            )
        ).json()
        changed = await quote(http, cart)
        assert changed.status_code == 429 and len(calls) == 1
    finally:
        await http.aclose()
        await app.state.freight_client.aclose()


async def test_backend_origin_context_change_renews_key_without_modifying_saved_request(
    prepared, db_engine
):
    http, calls, _, app, cart = prepared
    first = (await quote(http, cart)).json()
    old = record(db_engine, first["quote_reference"])
    previous = app.state.freight_client
    app.state.freight_client = PacksenviosClient(
        previous.settings.model_copy(update={"origin_postal_code": "20040002"}),
        transport=previous._http._transport,
    )
    try:
        second = (await quote(http, cart)).json()
        new = record(db_engine, second["quote_reference"])
        assert new["key"] != old["key"] and new["criteria"]["origin_postal_code"] == "20040002"
        assert record(db_engine, first["quote_reference"])["payload"] == old["payload"]
    finally:
        await previous.aclose()


async def test_selected_reference_has_database_quote_ownership_constraint(prepared, db_engine):
    http, _, _, _, cart = prepared
    first = (await quote(http, cart)).json()
    other = await make_cart(http, db_engine)
    second = (await quote(http, other)).json()
    with Session(db_engine) as session:
        saved = session.get(m.FreightQuote, UUID(first["quote_reference"]))
        saved.selected_option_snapshot_id = UUID(second["options"][0]["reference"])
        with testrunner.raises(IntegrityError):
            session.flush()
        session.rollback()
