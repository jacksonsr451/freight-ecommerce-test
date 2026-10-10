import hashlib
import json
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from freight_ecommerce.cart import service as carts
from freight_ecommerce.cart.schemas import BuyerDetails, DeliveryAddress
from freight_ecommerce.catalog.service import fail
from freight_ecommerce.domain.base import utcnow
from freight_ecommerce.domain.models import (
    Address,
    Cart,
    CheckoutAttempt,
    Customer,
    FreightOptionSnapshot,
    FreightQuote,
    Fulfillment,
    IntegrationAudit,
    Inventory,
    Order,
    OrderItem,
    PaymentSimulation,
    Product,
    StockReservation,
    TrackingEvent,
)
from freight_ecommerce.domain.states import (
    CartStatus,
    CheckoutStatus,
    FulfillmentStatus,
    OrderStatus,
    PaymentStatus,
    QuoteStatus,
)
from freight_ecommerce.freight.client import PacksenviosClient
from freight_ecommerce.orders.schemas import (
    CancelOrder,
    ConfirmPaymentSimulation,
    CreateOrder,
    FulfillmentView,
    OrderLineView,
    OrderList,
    OrderView,
    PaymentView,
    ShippingDestination,
)
from freight_ecommerce.quoting.packing import derive_request


def canonical_fingerprint(cart_id: UUID, revision: int) -> str:
    value = json.dumps(
        {"cart_id": str(cart_id), "expected_revision": revision},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode()).hexdigest()


def quote_for_order(session: Session, client: PacksenviosClient, cart: Cart, items):
    selected = session.execute(
        select(FreightOptionSnapshot, FreightQuote)
        .join(FreightQuote, FreightOptionSnapshot.quote_id == FreightQuote.id)
        .where(
            FreightQuote.cart_id == cart.id,
            FreightQuote.integration_scope == client.integration_scope,
            FreightQuote.mode == client.settings.mode,
            FreightQuote.cart_fingerprint == cart.commercial_fingerprint,
            FreightQuote.status == QuoteStatus.RECEIVED,
            FreightQuote.external_status == "quoted",
            FreightQuote.selected_option_snapshot_id == FreightOptionSnapshot.id,
            FreightOptionSnapshot.weight_only.is_(False),
        )
        .order_by(FreightQuote.created_at.desc(), FreightQuote.id)
        .limit(1)
        .with_for_update(of=FreightQuote)
    ).first()
    if selected is None:
        fail(
            409,
            "selected_freight_required",
            "Selecione uma oferta atual antes de criar o pedido local.",
        )
    option, quote = selected
    packing = "weight_only" if "length_cm" not in quote.criteria else "equal_volumes"
    try:
        request = derive_request(items, cart.delivery_address, packing, quote.request_key)
        prepared = client.prepare_quote(request)
    except (HTTPException, ValueError):
        fail(409, "quote_criteria_changed", "Recalcule o frete para o carrinho e destino atuais.")
    if prepared.criteria_fingerprint != quote.criteria_fingerprint:
        fail(409, "quote_criteria_changed", "Recalcule o frete para os valores atuais do catálogo.")
    if option.manual_only is None or option.demonstration_only is None:
        fail(
            409,
            "freight_review_required",
            "A condição comercial é desconhecida; revisão manual obrigatória.",
        )
    return option, quote


def view(session: Session, order: Order) -> OrderView:
    payment = session.scalar(
        select(PaymentSimulation).where(PaymentSimulation.order_id == order.id)
    )
    if payment is None:
        raise RuntimeError("Local order has no simulated payment record")
    option = session.get(FreightOptionSnapshot, order.freight_option_snapshot_id)
    fulfillment = session.scalar(select(Fulfillment).where(Fulfillment.order_id == order.id))
    cancellation = None
    if order.status == OrderStatus.PAYMENT_DECLINED:
        cancellation = "payment_declined"
    elif order.status == OrderStatus.CANCELLED:
        cancellation = "operator_cancelled"
    return OrderView(
        id=order.id,
        status=order.status,
        simulation=order.simulation,
        created_at=order.created_at,
        cart_revision=order.cart_revision,
        subtotal_cents=order.subtotal_cents,
        freight_cents=order.freight_cents,
        total_cents=order.total_cents,
        selected_option_reference=option.id,
        freight_review_required=option.manual_only is not False
        or option.demonstration_only is not False,
        shipping_destination=ShippingDestination(
            postal_code=order.shipping_address_snapshot["postal_code"],
            city=order.shipping_address_snapshot["city"],
            state=order.shipping_address_snapshot["state"],
        ),
        items=[
            OrderLineView(
                product_id=line.product_id,
                sku=line.sku,
                name=line.name,
                quantity=line.quantity,
                unit_price_cents=line.unit_price_cents,
                line_total_cents=line.line_total_cents,
                product_snapshot=line.product_snapshot,
            )
            for line in session.scalars(
                select(OrderItem)
                .where(OrderItem.order_id == order.id)
                .order_by(OrderItem.sku, OrderItem.product_id)
            )
        ],
        payment=PaymentView(
            id=payment.id,
            status=payment.status,
            amount_cents=payment.amount_cents,
            simulation=payment.simulation,
        ),
        fulfillment=FulfillmentView(status=fulfillment.status) if fulfillment else None,
        cancellation_reason=cancellation,
    )


def create(session: Session, client: PacksenviosClient, cart_id: UUID, command: CreateOrder):
    cart = carts.lock_cart(session, cart_id)
    fingerprint = canonical_fingerprint(cart_id, command.expected_revision)
    existing = session.scalar(
        select(Order).where(Order.submission_key == command.submission_key).with_for_update()
    )
    if existing is not None:
        if (
            existing.cart_revision != command.expected_revision
            or existing.submission_fingerprint != fingerprint
            or session.get(CheckoutAttempt, existing.checkout_attempt_id).cart_id != cart.id
        ):
            fail(
                409,
                "order_idempotency_conflict",
                "Chave da loja já utilizada com outro fechamento.",
            )
        return view(session, existing), False
    if not carts.is_editable(session, cart):
        fail(409, "cart_locked", "Carrinho encerrado ou já vinculado a pedido.")
    if cart.revision != command.expected_revision:
        fail(409, "cart_revision_conflict", "Carrinho mudou. Atualize antes de criar o pedido.")
    items = carts.current_items(session, cart)
    if carts.synchronize(session, cart, items):
        session.commit()
        fail(409, "cart_commercial_changed", "Catálogo mudou; recarregue e refaça a cotação.")
    if not items or any(item.problem is not None for item in items):
        fail(409, "cart_not_orderable", "Carrinho vazio ou com produtos indisponíveis.")
    if cart.buyer_details is None or cart.delivery_address is None:
        fail(422, "checkout_details_required", "Comprador e endereço válidos são necessários.")
    try:
        buyer = BuyerDetails.model_validate(cart.buyer_details)
        address = DeliveryAddress.model_validate(cart.delivery_address)
    except Exception:
        fail(422, "checkout_details_invalid", "Comprador ou endereço não são válidos.")
    option, quote = quote_for_order(session, client, cart, items)

    customer = cart.customer_id and session.get(Customer, cart.customer_id)
    if customer is not None:
        if customer.email.casefold() != str(buyer.email).casefold() or customer.name != buyer.name:
            fail(
                409,
                "cart_customer_conflict",
                "Comprador diverge da identidade local vinculada ao carrinho.",
            )
    else:
        existing_customer = session.scalar(
            select(Customer).where(func.lower(Customer.email) == str(buyer.email).casefold())
        )
        if existing_customer is not None:
            fail(
                409,
                "buyer_identity_conflict",
                "E-mail já vinculado a outra identidade local; "
                "não associamos compradores automaticamente.",
            )
        customer = Customer(name=buyer.name, email=str(buyer.email))
        session.add(customer)
        session.flush()
        cart.customer_id = customer.id
    address_row = Address(customer_id=customer.id, **address.model_dump())
    session.add(address_row)
    session.flush()
    attempt = CheckoutAttempt(
        cart_id=cart.id,
        customer_id=customer.id,
        address_id=address_row.id,
        cart_revision=cart.revision,
    )
    session.add(attempt)
    session.flush()
    attempt.transition(CheckoutStatus.QUOTING)
    attempt.transition(CheckoutStatus.QUOTED)
    if quote.checkout_attempt_id is None:
        quote.checkout_attempt_id = attempt.id
    elif quote.checkout_attempt_id != attempt.id:
        fail(
            409,
            "quote_attempt_already_bound",
            "Cotação já vinculada a outra tentativa local; refaça a cotação.",
        )

    subtotal = sum(item.line_total_cents for item in items)
    freight = option.price_cents
    order = Order(
        submission_key=command.submission_key,
        submission_fingerprint=fingerprint,
        checkout_attempt_id=attempt.id,
        customer_id=customer.id,
        freight_quote_id=quote.id,
        freight_option_snapshot_id=option.id,
        subtotal_cents=subtotal,
        freight_cents=freight,
        total_cents=subtotal + freight,
        simulation=True,
        cart_revision=cart.revision,
        cart_fingerprint=cart.commercial_fingerprint,
        shipping_address_snapshot=address.model_dump(mode="json"),
    )
    session.add(order)
    session.flush()
    for item in items:
        product = session.get(Product, item.product_id)
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                sku=product.sku,
                name=product.name,
                quantity=item.quantity,
                unit_price_cents=product.price_cents,
                line_total_cents=product.price_cents * item.quantity,
                product_snapshot={
                    "sku": product.sku,
                    "name": product.name,
                    "price_cents": product.price_cents,
                    "weight_grams": product.weight_grams,
                    "length_cm": product.length_cm,
                    "width_cm": product.width_cm,
                    "height_cm": product.height_cm,
                },
            )
        )
    payment_key = uuid5(NAMESPACE_URL, f"freight-ecommerce-local-payment/{command.submission_key}")
    payment = PaymentSimulation(
        order_id=order.id,
        idempotency_key=payment_key,
        amount_cents=order.total_cents,
        simulation=True,
    )
    session.add(payment)
    session.add(
        IntegrationAudit(
            correlation_id=uuid4(),
            checkout_attempt_id=attempt.id,
            quote_id=quote.id,
            operation="local_order_created",
            mode=quote.mode,
            outcome="started",
            request_key=quote.request_key,
            details={"simulation": True, "local_submission": True},
        )
    )
    session.flush()
    result = view(session, order)
    session.commit()
    return result, True


def order_items(session: Session, order_id: UUID):
    return session.scalars(
        select(OrderItem)
        .where(OrderItem.order_id == order_id)
        .order_by(OrderItem.product_id)
        .with_for_update()
    ).all()


def confirm(session: Session, order_id: UUID, command: ConfirmPaymentSimulation):
    initial = session.get(Order, order_id)
    if initial is None:
        fail(404, "order_not_found", "Pedido local não encontrado.")
    attempt = session.get(CheckoutAttempt, initial.checkout_attempt_id)
    cart = carts.lock_cart(session, attempt.cart_id)
    order = session.scalar(
        select(Order)
        .where(Order.id == order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    payment = session.scalar(
        select(PaymentSimulation)
        .where(PaymentSimulation.order_id == order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if command.expected_cart_revision != order.cart_revision:
        fail(409, "order_revision_conflict", "Revisão enviada não corresponde ao pedido criado.")
    final = {
        OrderStatus.PAID_SIMULATED: PaymentStatus.APPROVED,
        OrderStatus.PAYMENT_DECLINED: PaymentStatus.DECLINED,
    }
    if order.status in final:
        if command.outcome == final[order.status].value:
            return view(session, order), False
        fail(409, "payment_simulation_final", "Simulação já possui resultado final diferente.")
    if order.status != OrderStatus.PAYMENT_PENDING or payment.status != PaymentStatus.PENDING:
        fail(409, "order_not_confirmable", "Pedido não está aguardando simulação de pagamento.")
    if command.outcome == "pending":
        session.commit()
        return view(session, order), False
    if command.outcome == "declined":
        payment.transition(PaymentStatus.DECLINED)
        order.transition(OrderStatus.PAYMENT_DECLINED)
        cart.transition(CartStatus.ABANDONED)
        if attempt.status != CheckoutStatus.INVALIDATED:
            attempt.transition(CheckoutStatus.INVALIDATED)
        session.add(
            IntegrationAudit(
                correlation_id=uuid4(),
                checkout_attempt_id=attempt.id,
                quote_id=order.freight_quote_id,
                operation="local_payment_declined",
                mode="mock",
                outcome="succeeded",
                details={"simulation": True, "inventory_reserved": False},
            )
        )
        session.flush()
        result = view(session, order)
        session.commit()
        return result, True

    current_items = carts.current_items(session, cart)
    if any(item.problem == "insufficient_stock" for item in current_items):
        fail(409, "insufficient_stock", "Estoque insuficiente na confirmação do pedido.")
    if (
        cart.revision != order.cart_revision
        or cart.commercial_fingerprint != order.cart_fingerprint
        or cart.delivery_address is None
        or cart.buyer_details is None
        or not current_items
        or any(item.problem is not None for item in current_items)
    ):
        fail(
            409,
            "order_criteria_changed",
            "Carrinho mudou. Crie um novo pedido após revisar os critérios.",
        )
    lines = order_items(session, order.id)
    if len(lines) != len(current_items):
        fail(409, "order_items_changed", "Itens atuais diferem do snapshot do pedido.")
    current_by_id = {item.product_id: item for item in current_items}
    inventories = {}
    # Deterministic product UUID order prevents lock-order inversion across two orders.
    for line in lines:
        current = current_by_id.get(line.product_id)
        product = session.scalar(
            select(Product)
            .where(Product.id == line.product_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        inventory = session.scalar(
            select(Inventory)
            .where(Inventory.product_id == line.product_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if current is None or product is None or inventory is None or not product.active:
            fail(409, "order_product_unavailable", "Produto não está disponível para confirmação.")
        if (
            line.quantity != current.quantity
            or line.unit_price_cents != product.price_cents
            or line.sku != product.sku
            or line.name != product.name
            or line.product_snapshot.get("weight_grams") != product.weight_grams
            or line.product_snapshot.get("length_cm") != product.length_cm
            or line.product_snapshot.get("width_cm") != product.width_cm
            or line.product_snapshot.get("height_cm") != product.height_cm
        ):
            fail(
                409, "order_product_changed", "Preço ou medidas mudaram desde a criação do pedido."
            )
        if inventory.on_hand - inventory.reserved < line.quantity:
            fail(409, "insufficient_stock", "Estoque insuficiente na confirmação do pedido.")
        inventories[line.product_id] = inventory
    quote = session.get(FreightQuote, order.freight_quote_id)
    option = session.get(FreightOptionSnapshot, order.freight_option_snapshot_id)
    if (
        quote is None
        or option is None
        or quote.status != QuoteStatus.RECEIVED
        or quote.external_status != "quoted"
        or quote.cart_fingerprint != cart.commercial_fingerprint
        or quote.selected_option_snapshot_id != option.id
        or option.weight_only
        or option.price_cents != order.freight_cents
    ):
        fail(409, "order_freight_changed", "Snapshot de frete deixou de ser válido.")
    for line in lines:
        inventory = inventories[line.product_id]
        inventory.reserved += line.quantity
        session.add(
            StockReservation(
                order_id=order.id, product_id=line.product_id, quantity=line.quantity, active=True
            )
        )
    payment.transition(PaymentStatus.APPROVED)
    order.transition(OrderStatus.PAID_SIMULATED)
    attempt.transition(CheckoutStatus.CONFIRMED)
    cart.transition(CartStatus.CHECKED_OUT)
    fulfillment = Fulfillment(order_id=order.id, status=FulfillmentStatus.PAID_SIMULATED)
    session.add(fulfillment)
    session.flush()
    session.add(
        TrackingEvent(
            fulfillment_id=fulfillment.id,
            source="simulated",
            event_key="payment-approved",
            status="pago_simulado",
            title="Pagamento aprovado (simulação)",
            occurred_at=utcnow(),
            payload={"simulation": True, "source": "local_store"},
        )
    )
    session.add(
        IntegrationAudit(
            correlation_id=uuid4(),
            checkout_attempt_id=attempt.id,
            quote_id=quote.id,
            operation="local_payment_approved",
            mode="mock",
            outcome="succeeded",
            request_key=quote.request_key,
            details={"simulation": True, "inventory_reserved": True},
        )
    )
    result = view(session, order)
    session.commit()
    return result, True


def cancel(session: Session, order_id: UUID, command: CancelOrder):
    initial = session.get(Order, order_id)
    if initial is None:
        fail(404, "order_not_found", "Pedido local não encontrado.")
    attempt = session.get(CheckoutAttempt, initial.checkout_attempt_id)
    carts.lock_cart(session, attempt.cart_id)
    order = session.scalar(
        select(Order)
        .where(Order.id == order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if command.expected_cart_revision != order.cart_revision:
        fail(409, "order_revision_conflict", "Revisão enviada não corresponde ao pedido criado.")
    if order.status == OrderStatus.CANCELLED:
        return view(session, order), False
    if order.status != OrderStatus.PAID_SIMULATED:
        fail(
            409,
            "order_not_cancellable",
            "Somente pedido pago_simulado pode ser compensado neste fluxo.",
        )
    fulfillment = session.scalar(
        select(Fulfillment)
        .where(Fulfillment.order_id == order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if fulfillment is None or fulfillment.status != FulfillmentStatus.PAID_SIMULATED:
        fail(409, "fulfillment_started", "Fulfillment iniciado; compensação automática bloqueada.")
    reservations = session.scalars(
        select(StockReservation)
        .where(
            StockReservation.order_id == order.id,
            StockReservation.active.is_(True),
        )
        .order_by(StockReservation.product_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    for reservation in reservations:
        inventory = session.scalar(
            select(Inventory)
            .where(Inventory.product_id == reservation.product_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if inventory is None or inventory.reserved < reservation.quantity:
            fail(409, "reservation_inconsistent", "Reserva de estoque requer reconciliação local.")
        inventory.reserved -= reservation.quantity
        reservation.active = False
        reservation.released_at = utcnow()
    order.transition(OrderStatus.CANCELLED)
    fulfillment.transition(FulfillmentStatus.CANCELLED)
    session.add(
        TrackingEvent(
            fulfillment_id=fulfillment.id,
            source="simulated",
            event_key="order-cancelled",
            status="cancelado",
            title="Pedido cancelado (simulação local)",
            occurred_at=utcnow(),
            payload={"simulation": True, "stock_reservations_released": len(reservations)},
        )
    )
    session.add(
        IntegrationAudit(
            correlation_id=uuid4(),
            checkout_attempt_id=attempt.id,
            quote_id=order.freight_quote_id,
            operation="local_order_cancelled",
            mode="mock",
            outcome="succeeded",
            details={"simulation": True, "stock_reservations_released": len(reservations)},
        )
    )
    result = view(session, order)
    session.commit()
    return result, True


def get_order(session: Session, order_id: UUID) -> OrderView:
    order = session.get(Order, order_id)
    if order is None:
        fail(404, "order_not_found", "Pedido local não encontrado.")
    return view(session, order)


def list_orders(session: Session, cart_id: UUID, page: int, page_size: int) -> OrderList:
    if session.get(Cart, cart_id) is None:
        fail(404, "cart_not_found", "Carrinho não encontrado.")
    statement = select(Order).join(CheckoutAttempt, Order.checkout_attempt_id == CheckoutAttempt.id)
    statement = statement.where(CheckoutAttempt.cart_id == cart_id)
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    orders = session.scalars(
        statement.order_by(Order.created_at.desc(), Order.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return OrderList(items=[view(session, order) for order in orders], total=total)
