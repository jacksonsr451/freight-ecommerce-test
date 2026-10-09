from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from freight_ecommerce.catalog.schemas import (
    AdminProductView,
    InventoryView,
    ProductCreate,
    ProductPatch,
    ProductView,
    StockCheckRequest,
    StockCheckResponse,
)
from freight_ecommerce.domain.models import Inventory, Product


def fail(status: int, code: str, message: str, **extra) -> None:
    raise HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


def view(product: Product, inventory: Inventory, *, admin=False):
    values = {
        "id": product.id,
        "sku": product.sku,
        "name": product.name,
        "price_cents": product.price_cents,
        "weight_grams": product.weight_grams,
        "length_cm": product.length_cm,
        "width_cm": product.width_cm,
        "height_cm": product.height_cm,
        "stock_available": inventory.on_hand - inventory.reserved,
        "status": "active" if product.active else "inactive",
    }
    if admin:
        return AdminProductView(
            **values,
            created_at=product.created_at,
            updated_at=product.updated_at,
            inventory=InventoryView(
                on_hand=inventory.on_hand,
                reserved=inventory.reserved,
                available=values["stock_available"],
                version=inventory.version,
            ),
        )
    return ProductView(**values)


def find_product(session: Session, product_id: UUID, *, admin=False, lock=False):
    statement = select(Product, Inventory).join(Inventory).where(Product.id == product_id)
    if not admin:
        statement = statement.where(Product.active.is_(True))
    if lock:
        statement = statement.with_for_update()
    row = session.execute(statement).first()
    if row is None:
        fail(404, "product_not_found", "Produto não encontrado.")
    return row


def list_products(session: Session, page: int, page_size: int, *, admin=False):
    statement = select(Product, Inventory).join(Inventory)
    if not admin:
        statement = statement.where(Product.active.is_(True))
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = session.execute(
        statement.order_by(Product.sku, Product.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [view(product, inventory, admin=admin) for product, inventory in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


def ensure_sku_available(session: Session, sku: str, product_id: UUID | None = None):
    statement = select(Product.id).where(func.upper(Product.sku) == sku)
    if product_id is not None:
        statement = statement.where(Product.id != product_id)
    if session.scalar(statement) is not None:
        fail(409, "sku_conflict", "SKU já cadastrado.")


def create_product(session: Session, data: ProductCreate) -> AdminProductView:
    ensure_sku_available(session, data.sku)
    values = data.model_dump(exclude={"status", "stock_on_hand"})
    product = Product(**values, active=data.status == "active")
    session.add(product)
    session.flush()
    inventory = Inventory(product_id=product.id, on_hand=data.stock_on_hand, reserved=0)
    session.add(inventory)
    session.commit()  # commit before serializing/sending the HTTP response
    return view(product, inventory, admin=True)


def update_product(session: Session, product_id: UUID, data: ProductPatch) -> AdminProductView:
    product, inventory = find_product(session, product_id, admin=True, lock=True)
    values = data.model_dump(exclude_unset=True)
    if "sku" in values:
        ensure_sku_available(session, values["sku"], product.id)
    if "stock_on_hand" in values:
        new_stock = values.pop("stock_on_hand")
        if new_stock < inventory.reserved:
            fail(
                409,
                "stock_below_reserved",
                "Estoque não pode ficar abaixo das unidades reservadas.",
            )
        inventory.on_hand = new_stock
    if "status" in values:
        product.active = values.pop("status") == "active"
    for field, value in values.items():
        setattr(product, field, value)
    session.commit()
    return view(product, inventory, admin=True)


def deactivate_product(session: Session, product_id: UUID) -> None:
    product, _ = find_product(session, product_id, admin=True, lock=True)
    product.active = False
    session.commit()


def check_stock(session: Session, product_id: UUID, data: StockCheckRequest) -> StockCheckResponse:
    product, inventory = find_product(session, product_id)
    available = inventory.on_hand - inventory.reserved
    if data.quantity > available:
        fail(409, "insufficient_stock", "Estoque insuficiente.", available_quantity=available)
    return StockCheckResponse(
        product_id=product.id,
        requested_quantity=data.quantity,
        available_quantity=available,
        unit_price_cents=product.price_cents,
        subtotal_cents=product.price_cents * data.quantity,
        total_weight_grams=product.weight_grams * data.quantity,
    )
