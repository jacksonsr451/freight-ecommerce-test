import hashlib
import json
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from freight_ecommerce.cart.schemas import (
    AddItem,
    CartItemView,
    CartView,
    ChangeAddress,
    ChangeQuantity,
    CheckoutDetails,
)
from freight_ecommerce.catalog.service import fail, find_product
from freight_ecommerce.domain.models import (
    Cart,
    CartItem,
    CheckoutAttempt,
    FreightQuote,
    Inventory,
    Order,
    Product,
)
from freight_ecommerce.domain.states import CartStatus, CheckoutStatus, QuoteStatus


def lock_cart(session: Session, cart_id: UUID) -> Cart:
    cart = session.scalar(
        select(Cart)
        .where(Cart.id == cart_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if cart is None:
        fail(404, "cart_not_found", "Carrinho não encontrado.")
    return cart


def is_editable(session: Session, cart: Cart) -> bool:
    if cart.status not in {CartStatus.ACTIVE, CartStatus.CHECKOUT_PENDING}:
        return False
    final_attempt = session.scalar(
        select(CheckoutAttempt.id)
        .where(
            CheckoutAttempt.cart_id == cart.id,
            CheckoutAttempt.status == CheckoutStatus.CONFIRMED,
        )
        .limit(1)
    )
    order = session.scalar(
        select(Order.id)
        .join(
            CheckoutAttempt,
            Order.checkout_attempt_id == CheckoutAttempt.id,
        )
        .where(CheckoutAttempt.cart_id == cart.id)
        .limit(1)
    )
    return final_attempt is None and order is None


def current_items(session: Session, cart: Cart) -> list[CartItemView]:
    # One statement gives a coherent catalog/inventory snapshot; no stock is modified.
    rows = session.execute(
        select(CartItem, Product, Inventory)
        .join(
            Product,
            CartItem.product_id == Product.id,
        )
        .outerjoin(Inventory, Inventory.product_id == Product.id)
        .where(
            CartItem.cart_id == cart.id,
        )
        .order_by(Product.sku, Product.id)
        .execution_options(populate_existing=True)
    ).all()
    items = []
    for item, product, inventory in rows:
        available = inventory.on_hand - inventory.reserved if inventory is not None else 0
        problem = None
        if not product.active:
            problem = "inactive_product"
        elif inventory is None:
            problem = "inventory_unavailable"
        elif item.quantity > available:
            problem = "insufficient_stock"
        items.append(
            CartItemView(
                id=item.id,
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                quantity=item.quantity,
                unit_price_cents=product.price_cents,
                line_total_cents=product.price_cents * item.quantity,
                weight_grams=product.weight_grams,
                line_weight_grams=product.weight_grams * item.quantity,
                length_cm=product.length_cm,
                width_cm=product.width_cm,
                height_cm=product.height_cm,
                available_quantity=available,
                problem=problem,
            )
        )
    return items


def fingerprint(cart: Cart, items: list[CartItemView]) -> str:
    values = []
    # Changes in stock that still satisfy the quantity do not alter the quote criteria.
    for item in sorted(items, key=lambda item: str(item.product_id)):
        values.append(item.model_dump(mode="json", exclude={"id", "available_quantity"}))
    context = {"items": values, "address": cart.delivery_address}
    if cart.buyer_details is not None:
        context["buyer"] = cart.buyer_details
    canonical = json.dumps(
        context,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def invalidate_open_quotes(session: Session, cart: Cart) -> None:
    attempts = session.scalars(
        select(CheckoutAttempt)
        .where(
            CheckoutAttempt.cart_id == cart.id,
            CheckoutAttempt.status != CheckoutStatus.CONFIRMED,
        )
        .order_by(CheckoutAttempt.id)
        .with_for_update()
    ).all()
    quotes = session.scalars(
        select(FreightQuote)
        .where(
            or_(
                FreightQuote.cart_id == cart.id,
                FreightQuote.checkout_attempt_id.in_([attempt.id for attempt in attempts]),
            ),
            FreightQuote.status != QuoteStatus.INVALIDATED,
        )
        .order_by(FreightQuote.id)
        .with_for_update()
    ).all()
    for quote in quotes:
        quote.transition(QuoteStatus.INVALIDATED)  # local state only; preserve criteria and IDs
    for attempt in attempts:
        if attempt.status != CheckoutStatus.INVALIDATED:
            attempt.transition(CheckoutStatus.INVALIDATED)
    if cart.status == CartStatus.CHECKOUT_PENDING:
        cart.transition(CartStatus.ACTIVE)


def touch(session: Session, cart: Cart, current_fingerprint: str) -> None:
    invalidate_open_quotes(session, cart)
    cart.revision += 1
    cart.commercial_fingerprint = current_fingerprint


def synchronize(session: Session, cart: Cart, items: list[CartItemView]) -> bool:
    calculated = fingerprint(cart, items)
    if cart.commercial_fingerprint == calculated:
        return False
    if cart.commercial_fingerprint is None:
        has_attempt = (
            session.scalar(
                select(CheckoutAttempt.id)
                .where(
                    CheckoutAttempt.cart_id == cart.id,
                )
                .limit(1)
            )
            is not None
        )
        if not has_attempt:
            cart.commercial_fingerprint = calculated  # bootstrap existing carts without a quote
            return False
    touch(session, cart, calculated)
    return True


def render(session: Session, cart: Cart, items: list[CartItemView], editable: bool) -> CartView:
    ready = (
        editable
        and bool(items)
        and all(item.problem is None for item in items)
        and cart.delivery_address is not None
    )
    has_quote = False
    if ready:
        has_quote = (
            session.scalar(
                select(FreightQuote.id)
                .outerjoin(CheckoutAttempt, FreightQuote.checkout_attempt_id == CheckoutAttempt.id)
                .where(
                    or_(
                        and_(
                            CheckoutAttempt.cart_id == cart.id,
                            CheckoutAttempt.cart_revision == cart.revision,
                            CheckoutAttempt.status == CheckoutStatus.QUOTED,
                        ),
                        and_(
                            FreightQuote.cart_id == cart.id,
                            FreightQuote.cart_fingerprint == cart.commercial_fingerprint,
                            FreightQuote.external_status == "quoted",
                        ),
                    ),
                    FreightQuote.status == QuoteStatus.RECEIVED,
                )
                .limit(1)
            )
            is not None
        )
    return CartView(
        id=cart.id,
        status=cart.status,
        revision=cart.revision,
        delivery_address=cart.delivery_address,
        buyer_details=cart.buyer_details,
        items=items,
        subtotal_cents=sum(item.line_total_cents for item in items),
        total_weight_grams=sum(item.line_weight_grams for item in items),
        total_quantity=sum(item.quantity for item in items),
        editable=editable,
        checkout_ready=ready,
        has_current_quote=has_quote,
    )


def create_cart(session: Session) -> CartView:
    cart = Cart()
    session.add(cart)
    session.flush()
    cart.commercial_fingerprint = fingerprint(cart, [])
    result = render(session, cart, [], True)
    session.commit()
    return result


def get_cart(session: Session, cart_id: UUID) -> CartView:
    cart = lock_cart(session, cart_id)
    editable = is_editable(session, cart)
    items = current_items(session, cart)
    if editable:
        synchronize(session, cart, items)
    result = render(session, cart, items, editable)
    session.commit()  # persist cache invalidation, never inventory reservations
    return result


def prepare_change(session: Session, cart_id: UUID, expected_revision: int) -> Cart:
    cart = lock_cart(session, cart_id)
    if not is_editable(session, cart):
        fail(409, "cart_locked", "Carrinho encerrado ou vinculado a pedido; alterações bloqueadas.")
    if expected_revision != cart.revision:
        fail(409, "cart_revision_conflict", "Carrinho mudou. Consulte a revisão atual.")
    if synchronize(session, cart, current_items(session, cart)):
        session.commit()  # only synchronize stale commercial data; do not apply the requested edit
        fail(
            409,
            "cart_commercial_changed",
            "Catálogo mudou. Recarregue o carrinho antes de alterar.",
        )
    return cart


def validate_quantity(session: Session, product_id: UUID, quantity: int) -> None:
    if quantity > 1000:
        fail(409, "item_quantity_limit", "Limite local de 1000 unidades por produto.")
    product, inventory = find_product(session, product_id)
    if quantity > inventory.on_hand - inventory.reserved:
        fail(
            409,
            "insufficient_stock",
            "Estoque insuficiente.",
            available_quantity=inventory.on_hand - inventory.reserved,
        )


def finish_change(session: Session, cart: Cart, *, changed: bool, checked_product=None) -> CartView:
    items = current_items(session, cart)
    if checked_product is not None:
        affected = next(item for item in items if item.product_id == checked_product)
        if affected.problem is not None:
            fail(409, "product_unavailable", "Produto ficou indisponível durante a alteração.")
    if changed:
        touch(session, cart, fingerprint(cart, items))
    result = render(session, cart, items, True)
    session.commit()
    return result


def add_item(session: Session, cart_id: UUID, data: AddItem) -> CartView:
    cart = prepare_change(session, cart_id, data.expected_revision)
    item = session.scalar(
        select(CartItem).where(CartItem.cart_id == cart.id, CartItem.product_id == data.product_id)
    )
    quantity = data.quantity + (item.quantity if item is not None else 0)
    validate_quantity(session, data.product_id, quantity)
    if item is None:
        count = len(current_items(session, cart))
        if count >= 100:
            fail(409, "cart_item_limit", "Limite local de 100 produtos distintos no carrinho.")
        session.add(CartItem(cart_id=cart.id, product_id=data.product_id, quantity=quantity))
    else:
        item.quantity = quantity
    return finish_change(session, cart, changed=True, checked_product=data.product_id)


def find_item(session: Session, cart: Cart, item_id: UUID) -> CartItem:
    item = session.scalar(
        select(CartItem).where(CartItem.cart_id == cart.id, CartItem.id == item_id)
    )
    if item is None:
        fail(404, "cart_item_not_found", "Item não encontrado neste carrinho.")
    return item


def change_quantity(
    session: Session, cart_id: UUID, item_id: UUID, data: ChangeQuantity
) -> CartView:
    cart = prepare_change(session, cart_id, data.expected_revision)
    item = find_item(session, cart, item_id)
    validate_quantity(session, item.product_id, data.quantity)
    changed = item.quantity != data.quantity
    item.quantity = data.quantity
    return finish_change(session, cart, changed=changed, checked_product=item.product_id)


def remove_item(session: Session, cart_id: UUID, item_id: UUID, expected_revision: int) -> CartView:
    cart = prepare_change(session, cart_id, expected_revision)
    session.delete(find_item(session, cart, item_id))
    return finish_change(session, cart, changed=True)


def change_address(session: Session, cart_id: UUID, data: ChangeAddress) -> CartView:
    cart = prepare_change(session, cart_id, data.expected_revision)
    address = data.address.model_dump(mode="json", exclude_none=True) if data.address else None
    changed = cart.delivery_address != address
    cart.delivery_address = address
    return finish_change(session, cart, changed=changed)


def save_checkout_details(session: Session, cart_id: UUID, data: CheckoutDetails) -> CartView:
    cart = prepare_change(session, cart_id, data.expected_revision)
    buyer = data.buyer.model_dump(mode="json")
    address = data.address.model_dump(mode="json", exclude_none=True)
    changed = cart.buyer_details != buyer or cart.delivery_address != address
    cart.buyer_details = buyer
    cart.delivery_address = address
    return finish_change(session, cart, changed=changed)
