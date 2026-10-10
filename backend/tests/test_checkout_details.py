import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from freight_ecommerce.catalog.seed import seed_demo_catalog
from freight_ecommerce.config import Settings
from freight_ecommerce.database import transaction
from freight_ecommerce.domain import models as m
from freight_ecommerce.main import create_app

pytestmark = [pytest.mark.postgres, pytest.mark.anyio]
ADDRESS = {
    "postal_code": "01001000",
    "street": "Rua sintética",
    "number": "1",
    "district": "Centro",
    "city": "São Paulo",
    "state": "SP",
    "country": "BR",
}
BUYER = {"name": "Comprador sintético", "email": "buyer@example.com"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def fixture(db_engine):
    with transaction(db_engine) as session:
        seed_demo_catalog(session)
        product = session.scalar(select(m.Product.id).where(m.Product.sku == "DEMO-BOOK"))
    app = create_app(Settings(_env_file=None, environment="test"), engine=db_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        cart = (await client.post("/api/carts", json={})).json()
        cart = (
            await client.post(
                f"/api/carts/{cart['id']}/items",
                json={
                    "expected_revision": cart["revision"],
                    "product_id": str(product),
                    "quantity": 1,
                },
            )
        ).json()
        yield client, cart
    if app.state.freight_client is not None:
        await app.state.freight_client.aclose()


async def test_buyer_address_saved_atomically_and_address_change_invalidates_selection(
    fixture, db_engine
):
    client, cart = fixture
    path = f"/api/carts/{cart['id']}/checkout-details"
    first = await client.put(
        path, json={"expected_revision": cart["revision"], "buyer": BUYER, "address": ADDRESS}
    )
    assert first.status_code == 200
    saved = first.json()
    assert (
        saved["buyer_details"] == BUYER and saved["delivery_address"]["postal_code"] == "01001000"
    )
    quoted = (
        await client.post(
            f"/api/carts/{cart['id']}/freight-quotes", json={"expected_revision": saved["revision"]}
        )
    ).json()
    chosen = await client.post(
        f"/api/carts/{cart['id']}/freight-quotes/{quoted['quote_reference']}/selection",
        json={
            "expected_revision": saved["revision"],
            "option_reference": quoted["options"][0]["reference"],
        },
    )
    assert chosen.status_code == 200
    unchanged = await client.put(
        path,
        json={
            "expected_revision": chosen.json()["cart_revision"],
            "buyer": BUYER,
            "address": ADDRESS,
        },
    )
    assert unchanged.json()["revision"] == chosen.json()["cart_revision"]
    buyer_change = await client.put(
        path,
        json={
            "expected_revision": unchanged.json()["revision"],
            "buyer": {"name": "Outro comprador sintético", "email": "other@example.com"},
            "address": ADDRESS,
        },
    )
    assert buyer_change.json()["revision"] == unchanged.json()["revision"] + 1
    assert not buyer_change.json()["has_current_quote"]
    changed = await client.put(
        path,
        json={
            "expected_revision": buyer_change.json()["revision"],
            "buyer": BUYER,
            "address": {**ADDRESS, "postal_code": "20040002"},
        },
    )
    assert changed.status_code == 200 and not changed.json()["has_current_quote"]
    old = (
        await client.get(f"/api/carts/{cart['id']}/freight-quotes/{quoted['quote_reference']}")
    ).json()
    assert old["status"] == "invalidated" and old["options"] == []
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(m.Customer)) == 0
        assert session.scalar(select(func.count()).select_from(m.Order)) == 0
        assert all(stock.reserved == 0 for stock in session.scalars(select(m.Inventory)))


@pytest.mark.parametrize(
    "buyer,address,extra",
    [
        ({**BUYER, "email": "invalid"}, ADDRESS, {}),
        ({**BUYER, "name": " "}, ADDRESS, {}),
        (BUYER, {**ADDRESS, "postal_code": "01001-000"}, {}),
        (BUYER, {**ADDRESS, "postal_code": 1001000}, {}),
        (BUYER, ADDRESS, {"customer_id": "00000000-0000-4000-8000-000000000001"}),
        ({**BUYER, "document": "invented"}, ADDRESS, {}),
    ],
)
async def test_invalid_or_identity_override_does_not_persist_partial_checkout(
    fixture, buyer, address, extra
):
    client, cart = fixture
    response = await client.put(
        f"/api/carts/{cart['id']}/checkout-details",
        json={"expected_revision": cart["revision"], "buyer": buyer, "address": address, **extra},
    )
    assert response.status_code == 422
    current = (await client.get(f"/api/carts/{cart['id']}")).json()
    assert current["revision"] == cart["revision"] and current["buyer_details"] is None
    assert current["delivery_address"] is None
