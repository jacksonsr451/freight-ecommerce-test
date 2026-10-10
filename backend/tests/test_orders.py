import asyncio
from uuid import UUID, uuid4

import pytest
from alembic import command
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from freight_ecommerce.catalog.seed import seed_demo_catalog
from freight_ecommerce.config import Settings
from freight_ecommerce.database import transaction
from freight_ecommerce.domain import models as m
from freight_ecommerce.domain.states import (
    CartStatus,
    FulfillmentStatus,
    OrderStatus,
)
from freight_ecommerce.freight.client import PacksenviosClient
from freight_ecommerce.freight.config import FreightSettings
from freight_ecommerce.freight.synthetic import SYNTHETIC_COMPANY_ID, SyntheticQuoteTransport
from freight_ecommerce.main import create_app

pytestmark = [pytest.mark.postgres, pytest.mark.anyio]
BUYER = {"name": "Comprador local sintético", "email": "order-buyer@example.com"}
ADDRESS = {
    "postal_code": "01001000",
    "street": "Rua sintética",
    "number": "1",
    "complement": None,
    "district": "Centro",
    "city": "São Paulo",
    "state": "SP",
    "country": "BR",
}
ADMIN_KEY = "synthetic-local-admin-key-for-tests-only"
ADMIN_HEADERS = {"X-Local-Admin-Key": ADMIN_KEY}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def shop(db_engine):
    with transaction(db_engine) as session:
        seed_demo_catalog(session)
    provider = SyntheticQuoteTransport("quoted")
    client = PacksenviosClient(
        FreightSettings(
            _env_file=None,
            mode="mock",
            company_id=SYNTHETIC_COMPANY_ID,
            origin_postal_code="01001000",
            integration_scope="synthetic-orders-test",
        ),
        transport=provider,
    )
    app = create_app(
        Settings(
            _env_file=None,
            environment="test",
            LOCAL_ADMIN_KEY=ADMIN_KEY,
        ),
        engine=db_engine,
        freight_client=client,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://shop.test") as http:
        yield http, db_engine, provider
    await http.aclose()
    await client.aclose()


async def setup_quote(http, db_engine, *, sku="DEMO-BOOK", quantity=2, select_option=True):
    cart = (await http.post("/api/carts", json={})).json()
    with Session(db_engine) as session:
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
    response = await http.put(
        f"/api/carts/{cart['id']}/checkout-details",
        json={
            "expected_revision": cart["revision"],
            "buyer": {**BUYER, "email": f"buyer-{uuid4().hex}@example.com"},
            "address": ADDRESS,
        },
    )
    assert response.status_code == 200
    cart = response.json()
    quote_response = await http.post(
        f"/api/carts/{cart['id']}/freight-quotes",
        json={
            "expected_revision": cart["revision"],
        },
    )
    assert quote_response.status_code == 200
    quote = quote_response.json()
    if select_option:
        response = await http.post(
            f"/api/carts/{cart['id']}/freight-quotes/{quote['quote_reference']}/selection",
            json={
                "expected_revision": cart["revision"],
                "option_reference": quote["options"][0]["reference"],
            },
        )
        assert response.status_code == 200
    return cart, quote


async def create_order(http, cart, key=None, extra=None):
    body = {
        "expected_revision": cart["revision"],
        "submission_key": str(key or uuid4()),
        **(extra or {}),
    }
    return await http.post(f"/api/carts/{cart['id']}/orders", json=body)


async def confirm(http, order, outcome, revision=None):
    return await http.post(
        f"/api/orders/{order['id']}/confirm",
        json={
            "expected_cart_revision": revision or order["cart_revision"],
            "outcome": outcome,
        },
    )


async def test_order_creation_freezes_authoritative_amount_and_replay_is_idempotent(shop):
    http, db, provider = shop
    cart, quote = await setup_quote(http, db, quantity=2)
    key = str(uuid4())
    created = await create_order(http, cart, key)
    assert created.status_code == 201
    order = created.json()
    assert order["status"] == "payment_pending" and order["simulation"] is True
    assert order["payment"] == {
        "id": order["payment"]["id"],
        "status": "pending",
        "amount_cents": 11770,
        "simulation": True,
    }
    assert order["subtotal_cents"] == 9180 and order["freight_cents"] == 2590
    assert order["total_cents"] == 11770 and order["freight_review_required"] is True
    assert order["shipping_destination"] == {
        "postal_code": "01001000",
        "city": "São Paulo",
        "state": "SP",
    }
    assert order["items"][0]["unit_price_cents"] == 4590
    assert order["items"][0]["line_total_cents"] == 9180
    replay = await create_order(http, cart, key)
    assert replay.status_code == 200 and replay.json() == order
    with Session(db) as session:
        assert session.scalar(select(func.count()).select_from(m.Order)) == 1
        assert session.scalar(select(func.count()).select_from(m.PaymentSimulation)) == 1
        assert session.scalar(select(func.count()).select_from(m.OrderItem)) == 1
        assert session.scalar(select(func.count()).select_from(m.CheckoutAttempt)) == 1
        assert session.scalar(select(func.count()).select_from(m.Customer)) == 1
        assert session.scalar(select(func.count()).select_from(m.Address)) == 1
        assert session.scalar(select(func.count()).select_from(m.StockReservation)) == 0
        assert session.get(m.Cart, UUID(cart["id"])).status == CartStatus.CHECKOUT_PENDING
        assert session.get(
            m.FreightQuote, UUID(quote["quote_reference"])
        ).selected_option_snapshot_id == UUID(quote["options"][0]["reference"])
    assert provider.by_key  # only quote mock transport; order did not post to it


async def test_idempotency_key_conflict_and_tampered_money_freight_are_rejected(shop):
    http, db, _ = shop
    first_cart, _ = await setup_quote(http, db, quantity=1)
    second_cart, _ = await setup_quote(http, db, sku="DEMO-MUG", quantity=1)
    key = str(uuid4())
    first = await create_order(http, first_cart, key)
    assert first.status_code == 201
    replay_elsewhere = await create_order(http, second_cart, key)
    assert replay_elsewhere.status_code == 409
    tampered = await create_order(
        http,
        second_cart,
        str(uuid4()),
        {
            "price_cents": 1,
            "freight_cents": 0,
            "option_reference": str(uuid4()),
        },
    )
    assert tampered.status_code == 422
    with Session(db) as session:
        assert session.scalar(select(func.count()).select_from(m.Order)) == 1
        assert session.scalar(select(func.count()).select_from(m.StockReservation)) == 0


@pytest.mark.parametrize(
    "outcome,order_status,payment_status,reserved",
    [
        ("pending", "payment_pending", "pending", 0),
        ("declined", "payment_declined", "declined", 0),
        ("approved", "paid_simulated", "approved", 2),
    ],
)
async def test_payment_simulation_outcomes_are_local_and_reserve_only_on_approval(
    shop,
    outcome,
    order_status,
    payment_status,
    reserved,
):
    http, db, _ = shop
    cart, _ = await setup_quote(http, db, quantity=2)
    order = (await create_order(http, cart)).json()
    result = await confirm(http, order, outcome)
    assert result.status_code == 200
    response = result.json()
    assert response["simulation"] is True
    assert response["status"] == order_status and response["payment"]["status"] == payment_status
    assert response["payment"]["simulation"] is True
    with Session(db) as session:
        inventory = session.scalar(
            select(m.Inventory).join(m.Product).where(m.Product.sku == "DEMO-BOOK")
        )
        assert inventory.on_hand == 12 and inventory.reserved == reserved
        assert session.scalar(select(func.count()).select_from(m.StockReservation)) == (
            1 if reserved else 0
        )
        if outcome == "approved":
            assert response["fulfillment"]["status"] == "pago_simulado"
            fulfillment = session.scalar(
                select(m.Fulfillment).where(m.Fulfillment.order_id == UUID(order["id"]))
            )
            event = session.scalar(
                select(m.TrackingEvent).where(m.TrackingEvent.fulfillment_id == fulfillment.id)
            )
            assert event.source == "simulated" and event.payload["simulation"] is True
        else:
            assert response["fulfillment"] is None


async def test_pending_can_be_approved_once_and_approve_replay_does_not_double_reserve(shop):
    http, db, _ = shop
    cart, _ = await setup_quote(http, db, quantity=4)
    order = (await create_order(http, cart)).json()
    assert (await confirm(http, order, "pending")).json()["payment"]["status"] == "pending"
    approved = await confirm(http, order, "approved")
    replay = await confirm(http, order, "approved")
    assert (
        approved.status_code == 200
        and replay.status_code == 200
        and replay.json() == approved.json()
    )
    conflict = await confirm(http, order, "declined")
    assert conflict.status_code == 409
    with Session(db) as session:
        stock = session.scalar(
            select(m.Inventory).join(m.Product).where(m.Product.sku == "DEMO-BOOK")
        )
        assert stock.reserved == 4
        assert session.scalar(select(func.count()).select_from(m.StockReservation)) == 1
        assert session.scalar(select(func.count()).select_from(m.TrackingEvent)) == 1


async def test_confirmation_revalidates_stock_price_product_and_quote_snapshot(shop):
    http, db, _ = shop
    cart, quote = await setup_quote(http, db, quantity=3)
    order = (await create_order(http, cart)).json()
    with transaction(db) as session:
        stock = session.scalar(
            select(m.Inventory).join(m.Product).where(m.Product.sku == "DEMO-BOOK")
        )
        stock.reserved = 10
    rejected_stock = await confirm(http, order, "approved")
    assert (
        rejected_stock.status_code == 409
        and rejected_stock.json()["detail"]["code"] == "insufficient_stock"
    )
    with Session(db) as session:
        assert session.get(m.Order, UUID(order["id"])).status == OrderStatus.PAYMENT_PENDING
        assert session.scalar(select(func.count()).select_from(m.StockReservation)) == 0
    with transaction(db) as session:
        stock = session.scalar(
            select(m.Inventory).join(m.Product).where(m.Product.sku == "DEMO-BOOK")
        )
        stock.reserved = 0
        session.scalar(select(m.Product).where(m.Product.sku == "DEMO-BOOK")).price_cents = 5000
    rejected_price = await confirm(http, order, "approved")
    assert (
        rejected_price.status_code == 409
        and rejected_price.json()["detail"]["code"] == "order_product_changed"
    )
    with Session(db) as session:
        assert session.scalar(select(func.count()).select_from(m.StockReservation)) == 0
        assert (
            session.scalar(
                select(m.FreightQuote).where(m.FreightQuote.id == UUID(quote["quote_reference"]))
            ).external_status
            == "quoted"
        )


async def test_cancel_approved_local_order_releases_reservation_once_and_records_simulated_event(
    shop,
):
    http, db, _ = shop
    cart, _ = await setup_quote(http, db, quantity=5)
    order = (await create_order(http, cart)).json()
    await confirm(http, order, "approved")
    cancelled = await http.post(
        f"/api/orders/{order['id']}/cancel",
        json={
            "expected_cart_revision": order["cart_revision"],
        },
    )
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["payment"]["status"] == "approved"
    replay = await http.post(
        f"/api/orders/{order['id']}/cancel", json={"expected_cart_revision": order["cart_revision"]}
    )
    assert replay.status_code == 200 and replay.json() == cancelled.json()
    with Session(db) as session:
        stock = session.scalar(
            select(m.Inventory).join(m.Product).where(m.Product.sku == "DEMO-BOOK")
        )
        reservation = session.scalar(
            select(m.StockReservation).where(m.StockReservation.order_id == UUID(order["id"]))
        )
        fulfillment = session.scalar(
            select(m.Fulfillment).where(m.Fulfillment.order_id == UUID(order["id"]))
        )
        assert (
            stock.reserved == 0
            and reservation.active is False
            and reservation.released_at is not None
        )
        assert fulfillment.status == FulfillmentStatus.CANCELLED
        assert session.scalar(select(func.count()).select_from(m.TrackingEvent)) == 2


async def test_cancel_refuses_after_fulfillment_started_without_releasing_stock(shop):
    http, db, _ = shop
    cart, _ = await setup_quote(http, db)
    order = (await create_order(http, cart)).json()
    await confirm(http, order, "approved")
    with transaction(db) as session:
        session.scalar(
            select(m.Fulfillment).where(m.Fulfillment.order_id == UUID(order["id"]))
        ).transition(FulfillmentStatus.PICKING)
    response = await http.post(
        f"/api/orders/{order['id']}/cancel", json={"expected_cart_revision": order["cart_revision"]}
    )
    assert (
        response.status_code == 409 and response.json()["detail"]["code"] == "fulfillment_started"
    )
    with Session(db) as session:
        stock = session.scalar(
            select(m.Inventory).join(m.Product).where(m.Product.sku == "DEMO-BOOK")
        )
        assert stock.reserved == 2


async def test_two_local_orders_compete_for_stock_under_sorted_inventory_locks(shop):
    http, db, _ = shop
    first_cart, _ = await setup_quote(http, db, quantity=7)
    second_cart, _ = await setup_quote(http, db, quantity=7)
    first = (await create_order(http, first_cart)).json()
    second = (await create_order(http, second_cart)).json()
    results = await asyncio.gather(
        confirm(http, first, "approved"), confirm(http, second, "approved")
    )
    assert sorted(response.status_code for response in results) == [200, 409]
    with Session(db) as session:
        inventory = session.scalar(
            select(m.Inventory).join(m.Product).where(m.Product.sku == "DEMO-BOOK")
        )
        assert inventory.on_hand == 12 and inventory.reserved == 7
        assert (
            session.scalar(
                select(func.count())
                .select_from(m.Order)
                .where(m.Order.status == OrderStatus.PAID_SIMULATED)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(m.StockReservation)
                .where(m.StockReservation.active.is_(True))
            )
            == 1
        )


async def test_order_history_is_cart_scoped_and_pagination_is_local(shop):
    http, db, _ = shop
    cart, _ = await setup_quote(http, db)
    order = (await create_order(http, cart)).json()
    page = await http.get(f"/api/carts/{cart['id']}/orders?page=1&page_size=1")
    assert page.status_code == 200 and page.json()["total"] == 1
    assert page.json()["items"][0]["id"] == order["id"]
    assert (await http.get(f"/api/orders/{order['id']}")).json() == order
    assert (await http.get(f"/api/orders/{uuid4()}")).status_code == 404
    assert (await http.get(f"/api/carts/{uuid4()}/orders")).status_code == 404


async def test_create_replay_returns_same_order_after_payment_finalized(shop):
    http, db, _ = shop
    cart, _ = await setup_quote(http, db)
    key = uuid4()
    order = (await create_order(http, cart, key)).json()
    await confirm(http, order, "approved")
    replay = await create_order(http, cart, key)
    assert replay.status_code == 200 and replay.json()["id"] == order["id"]
    conflict = await create_order(http, cart, uuid4())
    assert conflict.status_code == 409 and conflict.json()["detail"]["code"] == "cart_locked"


async def test_concurrent_double_submit_creates_one_order_and_one_payment(shop):
    http, db, _ = shop
    cart, _ = await setup_quote(http, db)
    key = str(uuid4())
    results = await asyncio.gather(create_order(http, cart, key), create_order(http, cart, key))
    assert sorted(result.status_code for result in results) == [200, 201]
    assert results[0].json() == results[1].json()
    with Session(db) as session:
        assert session.scalar(select(func.count()).select_from(m.Order)) == 1
        assert session.scalar(select(func.count()).select_from(m.PaymentSimulation)) == 1
        assert session.scalar(select(func.count()).select_from(m.CheckoutAttempt)) == 1


async def test_two_concurrent_approvals_reserve_once_and_replay_same_payment(shop):
    http, db, _ = shop
    cart, _ = await setup_quote(http, db, quantity=4)
    order = (await create_order(http, cart)).json()
    responses = await asyncio.gather(
        confirm(http, order, "approved"), confirm(http, order, "approved")
    )
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json() == responses[1].json()
    with Session(db) as session:
        inventory = session.scalar(
            select(m.Inventory).join(m.Product).where(m.Product.sku == "DEMO-BOOK")
        )
        assert inventory.reserved == 4
        assert session.scalar(select(func.count()).select_from(m.StockReservation)) == 1
        assert session.scalar(select(func.count()).select_from(m.TrackingEvent)) == 1


async def test_create_requires_a_current_locally_selected_freight_snapshot(shop):
    http, db, _ = shop
    cart, _ = await setup_quote(http, db, select_option=False)
    response = await create_order(http, cart)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "selected_freight_required"


async def test_order_migration_downgrade_refuses_to_drop_live_order_evidence(
    shop, db_engine, alembic_config
):
    http, _, _ = shop
    cart, _ = await setup_quote(http, db_engine)
    order = (await create_order(http, cart)).json()
    with db_engine.connect() as connection:
        schema = connection.scalar(select(func.current_schema()))
        connection.commit()
        config = alembic_config(connection, schema)
        with pytest.raises(DBAPIError, match="Downgrade 0005 is blocked"):
            command.downgrade(config, "0004")
        connection.rollback()
    with Session(db_engine) as session:
        assert session.get(m.Order, UUID(order["id"])) is not None
        assert session.scalar(select(func.count()).select_from(m.PaymentSimulation)) == 1


async def test_admin_fulfillment_transitions_are_local_audited_and_filterable(shop):
    http, db, provider = shop
    cart, _ = await setup_quote(http, db)
    order = (await create_order(http, cart)).json()
    pending = await http.get("/api/admin/orders", headers=ADMIN_HEADERS)
    assert pending.status_code == 200 and pending.json()["total"] == 1
    assert pending.json()["items"][0]["id"] == order["id"]
    premature = await http.post(
        f"/api/admin/orders/{order['id']}/fulfillment",
        headers=ADMIN_HEADERS,
        json={"expected_status": "pago_simulado", "status": "separando"},
    )
    assert premature.status_code == 409

    order = (await confirm(http, order, "approved")).json()
    stages = [
        "separando",
        "embalado",
        "pronto_para_importacao",
        "importacao_pendente",
        "expedido_simulado",
        "entregue_simulado",
    ]
    current = "pago_simulado"
    for target in stages:
        response = await http.post(
            f"/api/admin/orders/{order['id']}/fulfillment",
            headers=ADMIN_HEADERS,
            json={"expected_status": current, "status": target},
        )
        assert response.status_code == 200, response.text
        detail = response.json()
        assert detail["internal_fulfillment_status"] == target
        assert detail["external_status"] is None
        assert detail["order"]["fulfillment"]["status"] == target
        current = target

    detail = await http.get(f"/api/admin/orders/{order['id']}", headers=ADMIN_HEADERS)
    assert detail.status_code == 200
    data = detail.json()
    assert data["snapshots"]["freight_option"]["manual_only"] is True
    assert data["snapshots"]["products"][0]["sku"] == "DEMO-BOOK"
    timeline = data["timeline"]
    assert any(event["source"] == "local_store" for event in timeline)
    assert any(event["source"] == "simulated" for event in timeline)
    admin_events = [event for event in timeline if event["source"] == "local_admin"]
    assert len(admin_events) == len(stages)
    assert [event["internal_status"] for event in admin_events] == stages
    assert [event["occurred_at"] for event in admin_events] == sorted(
        event["occurred_at"] for event in admin_events
    )
    assert all(event["external_status"] is None for event in timeline)
    assert admin_events[-1]["internal_status"] == "entregue_simulado"
    filtered = await http.get(
        "/api/admin/orders?order_status=paid_simulated&fulfillment_status=entregue_simulado",
        headers=ADMIN_HEADERS,
    )
    assert filtered.status_code == 200 and filtered.json()["total"] == 1
    assert provider.by_key  # only the previously-created synthetic quote was requested


async def test_admin_fulfillment_rejects_invalid_and_stale_transitions(shop):
    http, db, _ = shop
    cart, _ = await setup_quote(http, db)
    order = (await create_order(http, cart)).json()
    order = (await confirm(http, order, "approved")).json()
    path = f"/api/admin/orders/{order['id']}/fulfillment"
    invalid = await http.post(
        path,
        headers=ADMIN_HEADERS,
        json={"expected_status": "pago_simulado", "status": "entregue_simulado"},
    )
    assert invalid.status_code == 409
    stale = await http.post(
        path,
        headers=ADMIN_HEADERS,
        json={"expected_status": "embalado", "status": "separando"},
    )
    assert stale.status_code == 409
    with Session(db) as session:
        fulfillment = session.scalar(
            select(m.Fulfillment).where(m.Fulfillment.order_id == UUID(order["id"]))
        )
        assert fulfillment.status == FulfillmentStatus.PAID_SIMULATED
