import testrunner
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from freight_ecommerce.catalog.seed import seed_demo_catalog
from freight_ecommerce.config import Settings
from freight_ecommerce.database import transaction
from freight_ecommerce.domain.models import Inventory, Product
from freight_ecommerce.main import create_app

_testrunner_mark = [testrunner.mark.postgres]


async def test_search_filters_total_before_pagination_and_escapes_wildcards(db_engine):
    with transaction(db_engine) as session:
        seed_demo_catalog(session)
    app = create_app(Settings(_env_file=None, environment="test"), engine=db_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        found = await client.get("/api/products", params={"q": "DEMO", "page_size": 2, "page": 3})
        assert found.status_code == 200 and found.json()["total"] == 6
        assert len(found.json()["items"]) == 2
        book = await client.get("/api/products", params={"q": " liVro "})
        assert book.json()["total"] == 1 and book.json()["items"][0]["sku"] == "DEMO-BOOK"
        wildcard = await client.get("/api/products", params={"q": "%"})
        assert wildcard.json()["total"] == 0


async def test_stock_filter_uses_available_after_reservations_and_never_includes_inactive(
    db_engine,
):
    with transaction(db_engine) as session:
        seed_demo_catalog(session)
        book = session.scalar(select(Product).where(Product.sku == "DEMO-BOOK"))
        session.scalar(select(Inventory).where(Inventory.product_id == book.id)).reserved = 12
    app = create_app(Settings(_env_file=None, environment="test"), engine=db_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        out = await client.get("/api/products?in_stock=false")
        assert {product["sku"] for product in out.json()["items"]} == {
            "DEMO-BOOK",
            "DEMO-OUTOFSTOCK",
        }
        available = await client.get("/api/products?in_stock=true")
        assert available.json()["total"] == 4
