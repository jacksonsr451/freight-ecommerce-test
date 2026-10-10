import testrunner
from _testrunner_support import async_fixture
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from freight_ecommerce.catalog import seed
from freight_ecommerce.catalog.seed import DEMO_PRODUCTS, seed_demo_catalog
from freight_ecommerce.config import Settings
from freight_ecommerce.database import transaction
from freight_ecommerce.domain.models import Inventory, Product
from freight_ecommerce.main import create_app

_testrunner_mark = [testrunner.mark.postgres]
ADMIN_HEADERS = {"X-Local-Admin-Key": "synthetic-local-admin-key-for-tests-only"}
VALID_PRODUCT = {
    "sku": "SYNTHETIC-API",
    "name": "Produto sintético via API",
    "price_cents": 2590,
    "weight_grams": 1500,
    "length_cm": 20,
    "width_cm": 15,
    "height_cm": 10,
    "stock_on_hand": 5,
    "status": "active",
}


@async_fixture
async def catalog_client(db_engine):
    with transaction(db_engine) as session:
        seed_demo_catalog(session)
    app = create_app(
        Settings(
            _env_file=None, environment="test", LOCAL_ADMIN_KEY=ADMIN_HEADERS["X-Local-Admin-Key"]
        ),
        engine=db_engine,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_public_pagination_and_detail_hide_inactive_but_show_out_of_stock(catalog_client):
    seen = []
    for page in (1, 2, 3):
        response = await catalog_client.get("/api/products", params={"page": page, "page_size": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 6 and data["total_pages"] == 3
        assert data["page_size"] == 2 and data["page"] == page
        seen.extend(data["items"])
    assert len({item["id"] for item in seen}) == 6
    assert [item["sku"] for item in seen] == sorted(item["sku"] for item in seen)
    assert all(item["status"] == "active" for item in seen)
    exhausted = next(item for item in seen if item["sku"] == "DEMO-OUTOFSTOCK")
    assert exhausted["stock_available"] == 0
    detail = await catalog_client.get(f"/api/products/{seen[0]['id']}")
    assert detail.json() == seen[0]
    beyond = await catalog_client.get("/api/products?page=99&page_size=2")
    assert beyond.status_code == 200 and beyond.json()["items"] == []
    admin = await catalog_client.get("/api/admin/products", headers=ADMIN_HEADERS)
    assert admin.json()["total"] == 7
    inactive = next(item for item in admin.json()["items"] if item["status"] == "inactive")
    assert (await catalog_client.get(f"/api/products/{inactive['id']}")).status_code == 404
    assert (
        await catalog_client.post(
            f"/api/products/{inactive['id']}/stock-check",
            json={"quantity": 1},
        )
    ).status_code == 404


async def test_admin_crud_is_atomic_and_delete_is_logical(catalog_client, db_engine):
    response = await catalog_client.post(
        "/api/admin/products", headers=ADMIN_HEADERS, json=VALID_PRODUCT
    )
    assert response.status_code == 201
    created = response.json()
    product_id = created["id"]
    assert type(created["price_cents"]) is int and created["price_cents"] == 2590
    assert created["inventory"]["on_hand"] == 5 and created["inventory"]["reserved"] == 0
    assert created["weight_grams"] == 1500
    response = await catalog_client.patch(
        f"/api/admin/products/{product_id}",
        headers=ADMIN_HEADERS,
        json={"price_cents": 1790, "stock_on_hand": 4, "status": "inactive"},
    )
    assert response.status_code == 200
    assert response.json()["price_cents"] == 1790 and response.json()["inventory"]["on_hand"] == 4
    assert (await catalog_client.get(f"/api/products/{product_id}")).status_code == 404
    detail = await catalog_client.get(f"/api/admin/products/{product_id}", headers=ADMIN_HEADERS)
    assert detail.status_code == 200 and detail.json()["status"] == "inactive"
    await catalog_client.patch(
        f"/api/admin/products/{product_id}", headers=ADMIN_HEADERS, json={"status": "active"}
    )
    assert (await catalog_client.get(f"/api/products/{product_id}")).status_code == 200
    for _ in range(2):
        deleted = await catalog_client.delete(
            f"/api/admin/products/{product_id}", headers=ADMIN_HEADERS
        )
        assert deleted.status_code == 204 and deleted.content == b""
    with Session(db_engine) as session:
        product = session.scalar(select(Product).where(Product.sku == VALID_PRODUCT["sku"]))
        assert product is not None and not product.active
        assert session.scalar(select(func.count()).select_from(Inventory)) == 8


async def test_stock_check_uses_reserved_stock_and_authoritative_commercial_values(
    catalog_client, db_engine
):
    with transaction(db_engine) as session:
        product = session.scalar(select(Product).where(Product.sku == "DEMO-MUG"))
        product_id = str(product.id)
        inventory = session.scalar(select(Inventory).where(Inventory.product_id == product.id))
        inventory.reserved = 2
    path = f"/api/products/{product_id}/stock-check"
    response = await catalog_client.post(path, json={"quantity": 2})
    assert response.status_code == 200
    assert response.json() == {
        "product_id": product_id,
        "requested_quantity": 2,
        "available_quantity": 5,
        "unit_price_cents": 3490,
        "subtotal_cents": 6980,
        "total_weight_grams": 720,
    }
    insufficient = await catalog_client.post(path, json={"quantity": 6})
    assert insufficient.status_code == 409
    assert insufficient.json()["detail"]["code"] == "insufficient_stock"
    assert insufficient.json()["detail"]["available_quantity"] == 5
    tampered = await catalog_client.post(path, json={"quantity": 1, "price_cents": 1})
    assert tampered.status_code == 422
    with Session(db_engine) as session:
        inventory = session.scalar(select(Inventory).where(Inventory.product_id == product.id))
        assert inventory.reserved == 2  # stock-check is not a reservation
    rejected = await catalog_client.patch(
        f"/api/admin/products/{product_id}",
        headers=ADMIN_HEADERS,
        json={"stock_on_hand": 1, "price_cents": 10},
    )
    assert (
        rejected.status_code == 409 and rejected.json()["detail"]["code"] == "stock_below_reserved"
    )
    detail = (
        await catalog_client.get(f"/api/admin/products/{product_id}", headers=ADMIN_HEADERS)
    ).json()
    assert detail["inventory"]["on_hand"] == 7 and detail["price_cents"] == 3490


async def test_duplicate_sku_conflict_preserves_product_and_inventory(catalog_client, db_engine):
    duplicate = {**VALID_PRODUCT, "sku": " demo-book "}
    response = await catalog_client.post(
        "/api/admin/products", headers=ADMIN_HEADERS, json=duplicate
    )
    assert response.status_code == 409 and response.json()["detail"]["code"] == "sku_conflict"
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 7
        assert session.scalar(select(func.count()).select_from(Inventory)) == 7


async def test_inventory_insert_failure_rolls_back_new_product(catalog_client, db_engine):
    def fail_inventory_insert(mapper, connection, target):
        raise IntegrityError(
            "synthetic-private-insert", {}, RuntimeError("synthetic-private-detail")
        )

    event.listen(Inventory, "before_insert", fail_inventory_insert)
    try:
        response = await catalog_client.post(
            "/api/admin/products",
            headers=ADMIN_HEADERS,
            json=VALID_PRODUCT,
        )
    finally:
        event.remove(Inventory, "before_insert", fail_inventory_insert)
    assert response.status_code == 409
    assert "synthetic-private" not in response.text
    with Session(db_engine) as session:
        assert session.scalar(select(Product).where(Product.sku == VALID_PRODUCT["sku"])) is None
        assert session.scalar(select(func.count()).select_from(Inventory)) == 7


@testrunner.mark.parametrize(
    "field,value",
    [
        ("price_cents", -1),
        ("price_cents", 100_000_001),
        ("price_cents", 25.9),
        ("price_cents", "2590"),
        ("price_cents", True),
        ("weight_grams", 0),
        ("weight_grams", 50_000_001),
        ("length_cm", 301),
        ("width_cm", 0),
        ("height_cm", 1.5),
        ("stock_on_hand", -1),
        ("status", "invented"),
        ("sku", " "),
        ("name", "  "),
        ("reserved", 1),
    ],
)
async def test_invalid_admin_payload_is_rejected_without_partial_product(
    catalog_client, db_engine, field, value
):
    response = await catalog_client.post(
        "/api/admin/products",
        headers=ADMIN_HEADERS,
        json={**VALID_PRODUCT, field: value},
    )
    assert response.status_code == 422
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 7


@testrunner.mark.parametrize(
    "payload", [{}, {"price_cents": None}, {"reserved": 1}, {"price_cents": 1.2}]
)
async def test_patch_rejects_empty_null_and_unsupported_fields(catalog_client, payload):
    items = (await catalog_client.get("/api/products")).json()["items"]
    response = await catalog_client.patch(
        f"/api/admin/products/{items[0]['id']}",
        headers=ADMIN_HEADERS,
        json=payload,
    )
    assert response.status_code == 422


@testrunner.mark.parametrize("query", ["page=0", "page_size=0", "page_size=101"])
async def test_pagination_limits_are_validated(catalog_client, query):
    assert (await catalog_client.get(f"/api/products?{query}")).status_code == 422


@testrunner.mark.parametrize("quantity", [0, -1, 1.5, "1", True, 1001])
async def test_stock_quantity_is_strict_and_bounded(catalog_client, quantity):
    items = (await catalog_client.get("/api/products")).json()["items"]
    response = await catalog_client.post(
        f"/api/products/{items[0]['id']}/stock-check",
        json={"quantity": quantity},
    )
    assert response.status_code == 422


async def test_synthetic_seed_is_idempotent_and_preserves_operator_changes(db_engine):
    with transaction(db_engine) as session:
        assert seed_demo_catalog(session) == {"created": 7, "skipped": 0}
    with transaction(db_engine) as session:
        book = session.scalar(select(Product).where(Product.sku == "DEMO-BOOK"))
        book.price_cents = 100
        book.active = False
    with transaction(db_engine) as session:
        assert seed_demo_catalog(session) == {"created": 0, "skipped": 7}
        book = session.scalar(select(Product).where(Product.sku == "DEMO-BOOK"))
        assert book.price_cents == 100 and not book.active
        assert session.scalar(select(func.count()).select_from(Inventory)) == 7
    assert len({item.weight_grams for item in DEMO_PRODUCTS}) > 3


async def test_seed_entrypoint_executes_against_owned_schema(db_engine, monkeypatch, capsys):
    monkeypatch.setattr(seed, "Settings", lambda: Settings(_env_file=None, environment="test"))
    monkeypatch.setattr(seed, "build_engine", lambda settings: db_engine)
    seed.main()
    assert "7 created, 0 preserved" in capsys.readouterr().out
    seed.main()
    assert "0 created, 7 preserved" in capsys.readouterr().out
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 7
