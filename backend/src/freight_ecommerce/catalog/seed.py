"""Idempotent demo-only seed. No real customers, fiscal documents or freight fixtures."""

from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from freight_ecommerce.catalog.schemas import ProductCreate
from freight_ecommerce.config import Settings
from freight_ecommerce.database import build_engine, transaction
from freight_ecommerce.domain.models import Inventory, Product

DEMO_PRODUCTS = tuple(
    ProductCreate(
        sku=sku,
        name=name,
        price_cents=price,
        weight_grams=weight,
        length_cm=length,
        width_cm=width,
        height_cm=height,
        stock_on_hand=stock,
        status=status,
    )
    for sku, name, price, weight, length, width, height, stock, status in [
        ("DEMO-BOOK", "Livro sintético de demonstração", 4590, 450, 23, 16, 3, 12, "active"),
        ("DEMO-MUG", "Caneca sintética de demonstração", 3490, 360, 12, 12, 10, 7, "active"),
        ("DEMO-BACKPACK", "Mochila sintética de demonstração", 13990, 820, 40, 30, 15, 4, "active"),
        ("DEMO-HEADPHONES", "Fone sintético de demonstração", 25990, 240, 20, 18, 8, 10, "active"),
        ("DEMO-LAMP", "Luminária sintética de demonstração", 18990, 2100, 55, 22, 18, 2, "active"),
        ("DEMO-OUTOFSTOCK", "Produto sintético esgotado", 4990, 500, 22, 14, 8, 0, "active"),
        ("DEMO-INACTIVE", "Produto sintético inativo", 9990, 700, 30, 20, 12, 8, "inactive"),
    ]
)


def seed_demo_catalog(session: Session) -> dict[str, int]:
    created = 0
    for data in DEMO_PRODUCTS:
        if session.scalar(select(Product.id).where(Product.sku == data.sku)) is not None:
            continue  # Never reset prices, status, reservations or stock edited by an operator.
        product = Product(
            id=uuid5(NAMESPACE_URL, f"freight-ecommerce-test/synthetic/{data.sku}"),
            **data.model_dump(exclude={"stock_on_hand", "status"}),
            active=data.status == "active",
        )
        session.add(product)
        session.flush()
        session.add(Inventory(product_id=product.id, on_hand=data.stock_on_hand, reserved=0))
        created += 1
    session.flush()
    return {"created": created, "skipped": len(DEMO_PRODUCTS) - created}


def main() -> None:
    settings = Settings()
    url = make_url(settings.database_url.get_secret_value())
    if settings.environment == "production" or url.host not in {
        "127.0.0.1",
        "localhost",
        "::1",
        "db",
    }:
        raise RuntimeError("Demo seed requires a development/test local PostgreSQL database")
    engine = build_engine(settings)
    try:
        with transaction(engine) as session:
            result = seed_demo_catalog(session)
        print(f"Synthetic catalog: {result['created']} created, {result['skipped']} preserved.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
