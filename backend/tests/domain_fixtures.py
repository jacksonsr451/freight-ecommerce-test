"""Explicitly synthetic data for the local model; not an observed Packsenvios response."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from freight_ecommerce.domain import models as m
from freight_ecommerce.domain.states import OrderStatus, PaymentStatus, QuoteStatus


def make_product(**overrides):
    return m.Product(
        **{
            "sku": f"SYNTHETIC-{uuid4().hex}",
            "name": "Produto sintético",
            "price_cents": 10000,
            "weight_grams": 1000,
            "length_cm": 20,
            "width_cm": 15,
            "height_cm": 10,
            **overrides,
        }
    )


def make_graph(session):
    product = make_product()
    customer = m.Customer(name="Cliente sintético", email=f"{uuid4().hex}@example.test")
    session.add_all([product, customer])
    session.flush()
    inventory = m.Inventory(product_id=product.id, on_hand=10, reserved=0)
    address = m.Address(
        customer_id=customer.id,
        postal_code="01001000",
        street="Rua sintética",
        number="1",
        district="Bairro sintético",
        city="São Paulo",
        state="SP",
        country="BR",
    )
    cart = m.Cart(customer_id=customer.id)
    session.add_all([inventory, address, cart])
    session.flush()
    item = m.CartItem(cart_id=cart.id, product_id=product.id, quantity=1)
    checkout = m.CheckoutAttempt(
        cart_id=cart.id,
        customer_id=customer.id,
        address_id=address.id,
        cart_revision=1,
    )
    session.add_all([item, checkout])
    session.flush()
    quote = m.FreightQuote(
        checkout_attempt_id=checkout.id,
        integration_scope="synthetic-organization",
        request_key=uuid4(),
        external_quote_request_id=uuid4(),
        external_status="quoted",
        criteria={"weight_kg": "1.000", "destination_postal_code": "01001000"},
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
        payload={
            "synthetic_fixture": True,
            "price_cents": 2590,
            "manual_only": True,
            "calculation_snapshot": {"components": [{"amount_cents": 2590}]},
        },
    )
    batch = m.ShipmentImportBatch(
        integration_scope="synthetic-organization",
        creator_reference="synthetic-creator",
        freight_company_id=uuid4(),
        filename="synthetic.csv",
        content_sha256="a" * 64,
        deduplication_key=uuid4().hex * 2,
        external_batch_id=uuid4(),
        external_status="queued",
    )
    session.add_all([option, batch])
    session.flush()
    order = m.Order(
        submission_key=uuid4(),
        checkout_attempt_id=checkout.id,
        customer_id=customer.id,
        freight_quote_id=quote.id,
        freight_option_snapshot_id=option.id,
        subtotal_cents=10000,
        freight_cents=2590,
        total_cents=12590,
        shipping_address_snapshot={"postal_code": "01001000", "synthetic_fixture": True},
    )
    session.add(order)
    session.flush()
    order.transition(OrderStatus.PAID_SIMULATED)
    line = m.OrderItem(
        order_id=order.id,
        product_id=product.id,
        sku=product.sku,
        name=product.name,
        quantity=1,
        unit_price_cents=10000,
        line_total_cents=10000,
        product_snapshot={"synthetic_fixture": True, "weight_grams": 1000},
    )
    payment = m.PaymentSimulation(order_id=order.id, amount_cents=12590, idempotency_key=uuid4())
    fulfillment = m.Fulfillment(
        order_id=order.id,
        import_batch_id=batch.id,
        import_row_number=3,
        historical_shipment_id=uuid4(),
        imported_shipment_id=str(uuid4()),
        public_shipment_code="SYNTHETIC-CODE",
    )
    session.add_all([line, payment, fulfillment])
    session.flush()
    payment.transition(PaymentStatus.APPROVED)
    tracking = m.TrackingEvent(
        fulfillment_id=fulfillment.id,
        source="simulated",
        event_key="synthetic-event",
        status="expedido_simulado",
        title="Evento sintético",
        occurred_at=datetime(2026, 10, 8, 12, tzinfo=UTC),
        payload={"synthetic_fixture": True},
    )
    audit = m.IntegrationAudit(
        correlation_id=uuid4(),
        checkout_attempt_id=checkout.id,
        quote_id=quote.id,
        import_batch_id=batch.id,
        operation="synthetic-quote",
        mode="mock",
        outcome="succeeded",
        http_status=200,
        latency_ms=1,
        request_key=quote.request_key,
        details={"synthetic_fixture": True},
    )
    session.add_all([tracking, audit])
    session.commit()
    return SimpleNamespace(**locals())
