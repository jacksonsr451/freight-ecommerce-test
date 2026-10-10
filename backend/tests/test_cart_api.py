import asyncio
from copy import deepcopy
from uuid import UUID, uuid4

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
from freight_ecommerce.domain.states import CartStatus, CheckoutStatus, QuoteStatus
from freight_ecommerce.main import create_app

_testrunner_mark = [testrunner.mark.postgres]
ADDRESS = {
    "postal_code": "01001000",
    "street": "Rua sintética",
    "number": "1",
    "district": "Bairro sintético",
    "city": "São Paulo",
    "state": "SP",
    "country": "BR",
}


@async_fixture
async def client(db_engine):
    with transaction(db_engine) as session:
        seed_demo_catalog(session)
    app = create_app(Settings(_env_file=None, environment="test"), engine=db_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def new_cart(client):
    response = await client.post("/api/carts", json={})
    assert response.status_code == 201
    return response.json()


def product_id(engine, sku="DEMO-BOOK"):
    with Session(engine) as session:
        return str(session.scalar(select(m.Product.id).where(m.Product.sku == sku)))


async def add(client, cart, product, quantity=1):
    return await client.post(
        f"/api/carts/{cart['id']}/items",
        json={
            "expected_revision": cart["revision"],
            "product_id": product,
            "quantity": quantity,
        },
    )


async def set_address(client, cart, address=ADDRESS):
    response = await client.put(
        f"/api/carts/{cart['id']}/address",
        json={
            "expected_revision": cart["revision"],
            "address": address,
        },
    )
    assert response.status_code == 200
    return response.json()


def attach_synthetic_quote(engine, cart_id):
    """Synthetic stored quote, not an observed HTTP response or an external operation."""
    with transaction(engine) as session:
        cart = session.get(m.Cart, UUID(cart_id))
        customer = m.Customer(name="Cliente sintético", email=f"{uuid4().hex}@example.test")
        session.add(customer)
        session.flush()
        address = m.Address(customer_id=customer.id, **ADDRESS)
        session.add(address)
        session.flush()
        cart.customer_id = customer.id
        attempt = m.CheckoutAttempt(
            cart_id=cart.id,
            cart_revision=cart.revision,
            customer_id=customer.id,
            address_id=address.id,
        )
        session.add(attempt)
        session.flush()
        attempt.transition(CheckoutStatus.QUOTING)
        attempt.transition(CheckoutStatus.QUOTED)
        quote = m.FreightQuote(
            checkout_attempt_id=attempt.id,
            integration_scope="synthetic-cart-organization",
            request_key=uuid4(),
            external_quote_request_id=uuid4(),
            external_status="quoted",
            criteria={"synthetic_fixture": True, "weight_kg": "0.450"},
            response={"synthetic_fixture": True, "data": {"status": "quoted"}},
        )
        session.add(quote)
        session.flush()
        quote.transition(QuoteStatus.RECEIVED)
        option = m.FreightOptionSnapshot(
            quote_id=quote.id,
            option_index=0,
            price_cents=2590,
            deadline_days=3,
            carrier_name="Transportadora sintética",
            manual_only=True,
            demonstration_only=True,
            weight_only=False,
            payload={"synthetic_fixture": True, "manual_only": True, "price_cents": 2590},
        )
        session.add(option)
        session.flush()
        cart.transition(CartStatus.CHECKOUT_PENDING)
        return {
            "quote": quote.id,
            "attempt": attempt.id,
            "option": option.id,
            "request_key": quote.request_key,
            "external_id": quote.external_quote_request_id,
            "criteria": deepcopy(quote.criteria),
            "response": deepcopy(quote.response),
            "payload": deepcopy(option.payload),
        }


def assert_quote_invalidated(engine, saved):
    with Session(engine) as session:
        quote = session.get(m.FreightQuote, saved["quote"])
        assert quote.status == QuoteStatus.INVALIDATED
        assert session.get(m.CheckoutAttempt, saved["attempt"]).status == CheckoutStatus.INVALIDATED
        assert quote.request_key == saved["request_key"]
        assert quote.external_quote_request_id == saved["external_id"]
        assert quote.criteria == saved["criteria"] and quote.response == saved["response"]
        assert quote.external_status == "quoted"  # Never invent a remote cancellation/invalidation.
        assert session.get(m.FreightOptionSnapshot, saved["option"]).payload == saved["payload"]


async def test_cart_persists_add_merge_set_remove_and_authoritative_totals(client, db_engine):
    cart = await new_cart(client)
    assert cart["revision"] == 1 and cart["items"] == []
    assert cart["subtotal_cents"] == cart["total_weight_grams"] == cart["total_quantity"] == 0
    assert not cart["checkout_ready"] and not cart["has_current_quote"]
    cart = (await add(client, cart, product_id(db_engine), 2)).json()
    assert cart["subtotal_cents"] == 9180 and cart["total_weight_grams"] == 900
    cart = (await add(client, cart, product_id(db_engine), 1)).json()
    assert len(cart["items"]) == 1 and cart["items"][0]["quantity"] == 3
    cart = (await add(client, cart, product_id(db_engine, "DEMO-MUG"), 2)).json()
    assert cart["subtotal_cents"] == 3 * 4590 + 2 * 3490
    assert cart["total_weight_grams"] == 3 * 450 + 2 * 360
    book = next(item for item in cart["items"] if item["sku"] == "DEMO-BOOK")
    cart = (
        await client.patch(
            f"/api/carts/{cart['id']}/items/{book['id']}",
            json={
                "expected_revision": cart["revision"],
                "quantity": 1,
            },
        )
    ).json()
    assert cart["subtotal_cents"] == 4590 + 2 * 3490
    cart = (
        await client.delete(
            f"/api/carts/{cart['id']}/items/{book['id']}",
            params={
                "expected_revision": cart["revision"],
            },
        )
    ).json()
    assert len(cart["items"]) == 1 and cart["subtotal_cents"] == 6980
    assert (await client.get(f"/api/carts/{cart['id']}")).json() == cart
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(m.CartItem)) == 1
        assert all(stock.reserved == 0 for stock in session.scalars(select(m.Inventory)))


@testrunner.mark.parametrize("kind", ["add", "quantity", "remove", "address", "clear_address"])
async def test_changes_invalidate_quote_and_preserve_ids_snapshots(client, db_engine, kind):
    cart = (await add(client, await new_cart(client), product_id(db_engine))).json()
    cart = await set_address(client, cart)
    saved = attach_synthetic_quote(db_engine, cart["id"])
    cart = (await client.get(f"/api/carts/{cart['id']}")).json()
    assert cart["has_current_quote"]
    if kind == "add":
        response = await add(client, cart, product_id(db_engine, "DEMO-MUG"))
    elif kind == "quantity":
        response = await client.patch(
            f"/api/carts/{cart['id']}/items/{cart['items'][0]['id']}",
            json={
                "expected_revision": cart["revision"],
                "quantity": 2,
            },
        )
    elif kind == "remove":
        response = await client.delete(
            f"/api/carts/{cart['id']}/items/{cart['items'][0]['id']}",
            params={"expected_revision": cart["revision"]},
        )
    else:
        destination = None if kind == "clear_address" else {**ADDRESS, "number": "2"}
        response = await client.put(
            f"/api/carts/{cart['id']}/address",
            json={
                "expected_revision": cart["revision"],
                "address": destination,
            },
        )
    assert response.status_code == 200
    assert response.json()["revision"] == cart["revision"] + 1
    assert response.json()["status"] == "active" and not response.json()["has_current_quote"]
    assert_quote_invalidated(db_engine, saved)


async def test_noop_quantity_and_address_keep_quote_and_revision(client, db_engine):
    cart = (await add(client, await new_cart(client), product_id(db_engine))).json()
    cart = await set_address(client, cart)
    saved = attach_synthetic_quote(db_engine, cart["id"])
    for response in [
        await client.patch(
            f"/api/carts/{cart['id']}/items/{cart['items'][0]['id']}",
            json={
                "expected_revision": cart["revision"],
                "quantity": 1,
            },
        ),
        await client.put(
            f"/api/carts/{cart['id']}/address",
            json={
                "expected_revision": cart["revision"],
                "address": ADDRESS,
            },
        ),
    ]:
        assert response.status_code == 200 and response.json()["revision"] == cart["revision"]
        assert response.json()["has_current_quote"]
    with Session(db_engine) as session:
        assert session.get(m.FreightQuote, saved["quote"]).status == QuoteStatus.RECEIVED


@testrunner.mark.parametrize(
    "field,value",
    [
        ("price_cents", 9999),
        ("weight_grams", 900),
        ("length_cm", 24),
        ("active", False),
    ],
)
async def test_get_recalculates_catalog_and_invalidates_prior_quote(
    client, db_engine, field, value
):
    cart = (await add(client, await new_cart(client), product_id(db_engine))).json()
    cart = await set_address(client, cart)
    saved = attach_synthetic_quote(db_engine, cart["id"])
    with transaction(db_engine) as session:
        setattr(session.get(m.Product, UUID(cart["items"][0]["product_id"])), field, value)
    refreshed = (await client.get(f"/api/carts/{cart['id']}")).json()
    assert refreshed["revision"] == cart["revision"] + 1
    assert not refreshed["has_current_quote"]
    if field == "price_cents":
        assert refreshed["subtotal_cents"] == value
    if field == "weight_grams":
        assert refreshed["total_weight_grams"] == value
    if field == "active":
        assert refreshed["items"][0]["problem"] == "inactive_product"
        assert not refreshed["checkout_ready"]
    assert_quote_invalidated(db_engine, saved)
    assert (await client.get(f"/api/carts/{cart['id']}")).json()["revision"] == refreshed[
        "revision"
    ]


async def test_stale_catalog_on_mutation_requires_reload_and_persists_invalidation(
    client, db_engine
):
    cart = (await add(client, await new_cart(client), product_id(db_engine))).json()
    cart = await set_address(client, cart)
    saved = attach_synthetic_quote(db_engine, cart["id"])
    with transaction(db_engine) as session:
        session.get(m.Product, UUID(cart["items"][0]["product_id"])).price_cents = 100
    response = await add(client, cart, product_id(db_engine, "DEMO-MUG"))
    assert (
        response.status_code == 409
        and response.json()["detail"]["code"] == "cart_commercial_changed"
    )
    refreshed = (await client.get(f"/api/carts/{cart['id']}")).json()
    assert refreshed["subtotal_cents"] == 100 and len(refreshed["items"]) == 1
    assert refreshed["revision"] == cart["revision"] + 1
    assert_quote_invalidated(db_engine, saved)


@testrunner.mark.parametrize(
    "sku,quantity,status",
    [
        ("DEMO-OUTOFSTOCK", 1, 409),
        ("DEMO-MUG", 8, 409),
        ("DEMO-INACTIVE", 1, 404),
    ],
)
async def test_inactive_or_insufficient_stock_does_not_change_cart(
    client, db_engine, sku, quantity, status
):
    cart = await new_cart(client)
    response = await add(client, cart, product_id(db_engine, sku), quantity)
    assert response.status_code == status
    assert (await client.get(f"/api/carts/{cart['id']}")).json() == cart


async def test_unknown_product_and_item_from_other_cart_are_rejected(client, db_engine):
    cart = await new_cart(client)
    assert (await add(client, cart, str(uuid4()))).status_code == 404
    other = (await add(client, await new_cart(client), product_id(db_engine))).json()
    path = f"/api/carts/{cart['id']}/items/{other['items'][0]['id']}"
    assert (
        await client.patch(path, json={"quantity": 2, "expected_revision": cart["revision"]})
    ).status_code == 404
    assert (
        await client.delete(path, params={"expected_revision": cart["revision"]})
    ).status_code == 404
    assert (await client.get(f"/api/carts/{other['id']}")).json() == other
    assert (await client.get(f"/api/carts/{uuid4()}")).status_code == 404


@testrunner.mark.parametrize("quantity", [0, -1, 1.5, "1", True, 1001])
async def test_invalid_quantity_is_not_coerced(client, db_engine, quantity):
    cart = await new_cart(client)
    response = await add(client, cart, product_id(db_engine), quantity)
    assert response.status_code == 422
    assert (await client.get(f"/api/carts/{cart['id']}")).json() == cart


@testrunner.mark.parametrize(
    "field", ["price_cents", "weight_grams", "subtotal_cents", "freight_company_id"]
)
async def test_client_cannot_supply_commercial_or_external_context_fields(client, db_engine, field):
    cart = await new_cart(client)
    response = await client.post(
        f"/api/carts/{cart['id']}/items",
        json={
            "expected_revision": cart["revision"],
            "product_id": product_id(db_engine),
            "quantity": 1,
            field: 1,
        },
    )
    assert response.status_code == 422
    assert (await client.get(f"/api/carts/{cart['id']}")).json() == cart


async def test_two_concurrent_updates_have_one_winner_without_lost_update(client, db_engine):
    cart = (await add(client, await new_cart(client), product_id(db_engine))).json()
    path = f"/api/carts/{cart['id']}/items/{cart['items'][0]['id']}"
    responses = await asyncio.gather(
        *[
            client.patch(path, json={"expected_revision": cart["revision"], "quantity": quantity})
            for quantity in (2, 3)
        ]
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(response.json() for response in responses if response.status_code == 200)
    assert winner["revision"] == cart["revision"] + 1
    assert (await client.get(f"/api/carts/{cart['id']}")).json() == winner
    replay = await client.post(
        f"/api/carts/{cart['id']}/items",
        json={
            "expected_revision": cart["revision"],
            "product_id": product_id(db_engine),
            "quantity": 1,
        },
    )
    assert replay.status_code == 409
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(m.CartItem)) == 1


async def test_two_carts_share_availability_without_reserving_stock(client, db_engine):
    first, second = await new_cart(client), await new_cart(client)
    results = await asyncio.gather(
        add(client, first, product_id(db_engine), 12),
        add(client, second, product_id(db_engine), 12),
    )
    assert all(response.status_code == 200 for response in results)
    with Session(db_engine) as session:
        stock = session.scalar(
            select(m.Inventory).where(m.Inventory.product_id == UUID(product_id(db_engine)))
        )
        assert stock.on_hand == 12 and stock.reserved == 0


async def test_existing_item_reports_later_stock_shortage_and_can_be_removed(client, db_engine):
    cart = (await add(client, await new_cart(client), product_id(db_engine), 3)).json()
    cart = await set_address(client, cart)
    saved = attach_synthetic_quote(db_engine, cart["id"])
    with transaction(db_engine) as session:
        stock = session.scalar(
            select(m.Inventory).where(
                m.Inventory.product_id == UUID(cart["items"][0]["product_id"])
            )
        )
        stock.reserved = 11
    cart = (await client.get(f"/api/carts/{cart['id']}")).json()
    assert cart["items"][0]["problem"] == "insufficient_stock" and not cart["checkout_ready"]
    assert_quote_invalidated(db_engine, saved)
    removed = await client.delete(
        f"/api/carts/{cart['id']}/items/{cart['items'][0]['id']}",
        params={"expected_revision": cart["revision"]},
    )
    assert removed.status_code == 200 and removed.json()["items"] == []


async def test_closed_cart_cannot_change_or_invalidate_historical_quote(client, db_engine):
    cart = (await add(client, await new_cart(client), product_id(db_engine))).json()
    cart = await set_address(client, cart)
    saved = attach_synthetic_quote(db_engine, cart["id"])
    with transaction(db_engine) as session:
        session.get(m.Cart, UUID(cart["id"])).transition(CartStatus.CHECKED_OUT)
    response = await add(client, cart, product_id(db_engine))
    assert response.status_code == 409 and response.json()["detail"]["code"] == "cart_locked"
    assert not (await client.get(f"/api/carts/{cart['id']}")).json()["editable"]
    with Session(db_engine) as session:
        assert session.get(m.FreightQuote, saved["quote"]).status == QuoteStatus.RECEIVED


async def test_failed_mutation_rolls_back_cart_item_and_quote_states(client, db_engine):
    cart = (await add(client, await new_cart(client), product_id(db_engine))).json()
    cart = await set_address(client, cart)
    saved = attach_synthetic_quote(db_engine, cart["id"])

    def reject_cart_update(mapper, connection, target):
        raise IntegrityError("synthetic-cart-failure", {}, RuntimeError("synthetic-private-detail"))

    event.listen(m.Cart, "before_update", reject_cart_update)
    try:
        response = await client.patch(
            f"/api/carts/{cart['id']}/items/{cart['items'][0]['id']}",
            json={
                "expected_revision": cart["revision"],
                "quantity": 2,
            },
        )
    finally:
        event.remove(m.Cart, "before_update", reject_cart_update)
    assert response.status_code == 409 and "synthetic-private" not in response.text
    restored = (await client.get(f"/api/carts/{cart['id']}")).json()
    assert restored["revision"] == cart["revision"] and restored["items"][0]["quantity"] == 1
    assert restored["has_current_quote"]
    with Session(db_engine) as session:
        assert session.get(m.FreightQuote, saved["quote"]).status == QuoteStatus.RECEIVED


async def test_add_checks_total_existing_quantity_not_only_increment(client, db_engine):
    cart = (await add(client, await new_cart(client), product_id(db_engine), 10)).json()
    rejected = await add(client, cart, product_id(db_engine), 3)
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "insufficient_stock"
    assert (await client.get(f"/api/carts/{cart['id']}")).json() == cart


async def test_sufficient_stock_changes_and_unrelated_catalog_changes_keep_quote(client, db_engine):
    cart = (await add(client, await new_cart(client), product_id(db_engine))).json()
    cart = await set_address(client, cart)
    saved = attach_synthetic_quote(db_engine, cart["id"])
    with transaction(db_engine) as session:
        book_id = UUID(cart["items"][0]["product_id"])
        session.scalar(select(m.Inventory).where(m.Inventory.product_id == book_id)).reserved = 1
        session.scalar(select(m.Product).where(m.Product.sku == "DEMO-MUG")).price_cents = 100
    refreshed = (await client.get(f"/api/carts/{cart['id']}")).json()
    assert refreshed["revision"] == cart["revision"] and refreshed["has_current_quote"]
    assert refreshed["items"][0]["available_quantity"] == 11
    with Session(db_engine) as session:
        assert session.get(m.FreightQuote, saved["quote"]).status == QuoteStatus.RECEIVED


@testrunner.mark.parametrize(
    "address",
    [
        {**ADDRESS, "postal_code": "01001-000"},
        {**ADDRESS, "postal_code": 1001000},
        {**ADDRESS, "street": ""},
        {**ADDRESS, "country": "US"},
        {**ADDRESS, "freight_company_id": "synthetic-forbidden-context"},
    ],
)
async def test_invalid_destination_does_not_change_cart(client, address):
    cart = await new_cart(client)
    response = await client.put(
        f"/api/carts/{cart['id']}/address",
        json={
            "expected_revision": cart["revision"],
            "address": address,
        },
    )
    assert response.status_code == 422
    assert (await client.get(f"/api/carts/{cart['id']}")).json() == cart


@testrunner.mark.parametrize("revision", [0, True, "1", 1.5])
async def test_revision_is_required_as_strict_positive_integer(client, db_engine, revision):
    cart = await new_cart(client)
    response = await client.post(
        f"/api/carts/{cart['id']}/items",
        json={
            "expected_revision": revision,
            "product_id": product_id(db_engine),
            "quantity": 1,
        },
    )
    assert response.status_code == 422
    assert (await client.get(f"/api/carts/{cart['id']}")).json() == cart


async def test_confirmed_checkout_also_blocks_cart_even_before_status_is_closed(client, db_engine):
    cart = (await add(client, await new_cart(client), product_id(db_engine))).json()
    cart = await set_address(client, cart)
    saved = attach_synthetic_quote(db_engine, cart["id"])
    with transaction(db_engine) as session:
        session.get(m.CheckoutAttempt, saved["attempt"]).transition(CheckoutStatus.CONFIRMED)
    assert (await add(client, cart, product_id(db_engine))).status_code == 409
    with Session(db_engine) as session:
        assert session.get(m.FreightQuote, saved["quote"]).status == QuoteStatus.RECEIVED
