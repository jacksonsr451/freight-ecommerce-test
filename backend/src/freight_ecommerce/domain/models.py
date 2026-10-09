from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from freight_ecommerce.domain.base import Base, MutableRecord, Record, UTCDateTime
from freight_ecommerce.domain.states import (
    CartStatus,
    CheckoutStatus,
    FulfillmentStatus,
    ImportStatus,
    OrderStatus,
    PaymentStatus,
    QuoteStatus,
    Stateful,
    state_column,
)


class Product(MutableRecord, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price_cents >= 0", name="price_nonnegative"),
        CheckConstraint("weight_grams BETWEEN 1 AND 50000000", name="weight_range"),
        CheckConstraint(
            "length_cm BETWEEN 1 AND 300 AND width_cm BETWEEN 1 AND 300 "
            "AND height_cm BETWEEN 1 AND 300",
            name="dimensions_range",
        ),
    )
    sku: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    price_cents: Mapped[int] = mapped_column(BigInteger)
    weight_grams: Mapped[int] = mapped_column(Integer)
    length_cm: Mapped[int] = mapped_column(Integer)
    width_cm: Mapped[int] = mapped_column(Integer)
    height_cm: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Inventory(MutableRecord, Base):
    __tablename__ = "inventories"
    __table_args__ = (
        CheckConstraint(
            "on_hand >= 0 AND reserved >= 0 AND reserved <= on_hand", name="stock_range"
        ),
    )
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"), unique=True)
    on_hand: Mapped[int] = mapped_column(default=0, server_default="0")
    reserved: Mapped[int] = mapped_column(default=0, server_default="0")
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class Customer(MutableRecord, Base):
    __tablename__ = "customers"
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(254))
    __table_args__ = (Index("uq_customers_email_normalized", text("lower(email)"), unique=True),)


class Address(MutableRecord, Base):
    __tablename__ = "addresses"
    __table_args__ = (
        UniqueConstraint("id", "customer_id"),
        CheckConstraint("postal_code ~ '^[0-9]{8}$'", name="postal_code_format"),
        CheckConstraint("char_length(state) = 2 AND country = 'BR'", name="country_state"),
    )
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    postal_code: Mapped[str] = mapped_column(String(8))
    street: Mapped[str] = mapped_column(String(255))
    number: Mapped[str] = mapped_column(String(32))
    complement: Mapped[str | None] = mapped_column(String(120))
    district: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(2))
    country: Mapped[str] = mapped_column(String(2), default="BR", server_default="BR")


class Cart(Stateful, MutableRecord, Base):
    __tablename__ = "carts"
    __table_args__ = (
        CheckConstraint("revision > 0", name="revision_positive"),
        CheckConstraint(
            "delivery_address IS NULL OR jsonb_typeof(delivery_address) = 'object'",
            name="delivery_address_object",
        ),
        CheckConstraint(
            "commercial_fingerprint IS NULL OR char_length(commercial_fingerprint) = 64",
            name="commercial_fingerprint_length",
        ),
    )
    initial_status = CartStatus.ACTIVE
    status: Mapped[CartStatus] = state_column(CartStatus, initial_status)
    customer_id: Mapped[UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    revision: Mapped[int] = mapped_column(default=1, server_default="1")
    delivery_address: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    commercial_fingerprint: Mapped[str | None] = mapped_column(String(64))


class CartItem(MutableRecord, Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("cart_id", "product_id"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )
    cart_id: Mapped[UUID] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)


class CheckoutAttempt(Stateful, MutableRecord, Base):
    __tablename__ = "checkout_attempts"
    __table_args__ = (
        UniqueConstraint("id", "customer_id"),
        ForeignKeyConstraint(
            ["address_id", "customer_id"], ["addresses.id", "addresses.customer_id"]
        ),
        CheckConstraint("cart_revision > 0", name="cart_revision_positive"),
    )
    initial_status = CheckoutStatus.CREATED
    status: Mapped[CheckoutStatus] = state_column(CheckoutStatus, initial_status)
    cart_id: Mapped[UUID] = mapped_column(ForeignKey("carts.id"), index=True)
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    address_id: Mapped[UUID] = mapped_column(index=True)
    cart_revision: Mapped[int] = mapped_column(Integer)


class FreightQuote(Stateful, MutableRecord, Base):
    __tablename__ = "freight_quotes"
    __table_args__ = (
        UniqueConstraint(
            "integration_scope", "request_key", name="uq_freight_quotes_scope_request_key"
        ),
        UniqueConstraint(
            "integration_scope",
            "external_quote_request_id",
            name="uq_freight_quotes_scope_external_id",
        ),
        UniqueConstraint("id", "checkout_attempt_id"),
        CheckConstraint("jsonb_typeof(criteria) = 'object'", name="criteria_object"),
    )
    initial_status = QuoteStatus.REQUESTED
    status: Mapped[QuoteStatus] = state_column(QuoteStatus, initial_status)
    checkout_attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("checkout_attempts.id"), index=True
    )
    # Local integration namespace, never sent as a tenant selector to Packsenvios.
    integration_scope: Mapped[str] = mapped_column(String(128))
    request_key: Mapped[UUID] = mapped_column()
    external_quote_request_id: Mapped[UUID | None] = mapped_column(active_history=True)
    external_status: Mapped[str | None] = mapped_column(String(80))
    criteria: Mapped[dict[str, Any]] = mapped_column(JSONB)
    response: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True), active_history=True
    )


class FreightOptionSnapshot(Record, Base):
    __tablename__ = "freight_option_snapshots"
    __table_args__ = (
        UniqueConstraint("quote_id", "option_index"),
        UniqueConstraint("id", "quote_id", "price_cents"),
        CheckConstraint("option_index >= 0", name="option_index_nonnegative"),
        CheckConstraint("price_cents >= 0", name="price_nonnegative"),
        CheckConstraint("deadline_days IS NULL OR deadline_days >= 0", name="deadline_nonnegative"),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="payload_object"),
    )
    quote_id: Mapped[UUID] = mapped_column(ForeignKey("freight_quotes.id"), index=True)
    option_index: Mapped[int] = mapped_column(Integer)
    price_cents: Mapped[int] = mapped_column(BigInteger)
    deadline_days: Mapped[int | None] = mapped_column(Integer)
    carrier_name: Mapped[str] = mapped_column(String(160))
    manual_only: Mapped[bool] = mapped_column(Boolean)
    demonstration_only: Mapped[bool] = mapped_column(Boolean)
    weight_only: Mapped[bool] = mapped_column(Boolean)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)

    def require_automatic_contract_eligibility(self) -> None:
        if self.manual_only or self.demonstration_only or self.weight_only:
            raise ValueError("Offer is not eligible for automatic contracting")
        # No contract adapter exists: absence of flags does not establish external eligibility.
        raise NotImplementedError("TODO-CONTRACT: external eligibility is not implemented")


class Order(Stateful, MutableRecord, Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("id", "total_cents"),
        ForeignKeyConstraint(
            ["checkout_attempt_id", "customer_id"],
            ["checkout_attempts.id", "checkout_attempts.customer_id"],
        ),
        ForeignKeyConstraint(
            ["freight_quote_id", "checkout_attempt_id"],
            ["freight_quotes.id", "freight_quotes.checkout_attempt_id"],
        ),
        ForeignKeyConstraint(
            ["freight_option_snapshot_id", "freight_quote_id", "freight_cents"],
            [
                "freight_option_snapshots.id",
                "freight_option_snapshots.quote_id",
                "freight_option_snapshots.price_cents",
            ],
        ),
        CheckConstraint(
            "(freight_quote_id IS NULL AND freight_option_snapshot_id IS NULL "
            "AND freight_cents = 0) OR (freight_quote_id IS NOT NULL "
            "AND freight_option_snapshot_id IS NOT NULL)",
            name="freight_selection_pair",
        ),
        CheckConstraint(
            "subtotal_cents >= 0 AND freight_cents >= 0 AND discount_cents >= 0 "
            "AND total_cents >= 0 AND total_cents = subtotal_cents + freight_cents "
            "- discount_cents",
            name="totals_consistent",
        ),
        CheckConstraint("simulation", name="simulation_required"),
        CheckConstraint(
            "jsonb_typeof(shipping_address_snapshot) = 'object'", name="address_object"
        ),
    )
    initial_status = OrderStatus.PAYMENT_PENDING
    status: Mapped[OrderStatus] = state_column(OrderStatus, initial_status)
    submission_key: Mapped[UUID] = mapped_column(unique=True)
    checkout_attempt_id: Mapped[UUID] = mapped_column(unique=True)
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    freight_quote_id: Mapped[UUID | None] = mapped_column(index=True)
    freight_option_snapshot_id: Mapped[UUID | None] = mapped_column(index=True)
    subtotal_cents: Mapped[int] = mapped_column(BigInteger)
    freight_cents: Mapped[int] = mapped_column(BigInteger)
    discount_cents: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    total_cents: Mapped[int] = mapped_column(BigInteger)
    simulation: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    shipping_address_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)


class OrderItem(Record, Base):
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id"),
        CheckConstraint(
            "quantity > 0 AND unit_price_cents >= 0 "
            "AND line_total_cents = quantity::bigint * unit_price_cents",
            name="line_total",
        ),
        CheckConstraint("jsonb_typeof(product_snapshot) = 'object'", name="product_object"),
    )
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"), index=True)
    sku: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    line_total_cents: Mapped[int] = mapped_column(BigInteger)
    product_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)


class PaymentSimulation(Stateful, MutableRecord, Base):
    __tablename__ = "payment_simulations"
    __table_args__ = (
        ForeignKeyConstraint(["order_id", "amount_cents"], ["orders.id", "orders.total_cents"]),
        CheckConstraint("simulation AND amount_cents >= 0", name="simulation_amount"),
    )
    initial_status = PaymentStatus.PENDING
    status: Mapped[PaymentStatus] = state_column(PaymentStatus, initial_status)
    order_id: Mapped[UUID] = mapped_column(index=True)
    idempotency_key: Mapped[UUID] = mapped_column(unique=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    simulation: Mapped[bool] = mapped_column(default=True, server_default=text("true"))


class ShipmentImportBatch(Stateful, MutableRecord, Base):
    __tablename__ = "shipment_import_batches"
    __table_args__ = (
        UniqueConstraint("integration_scope", "external_batch_id"),
        CheckConstraint("char_length(content_sha256) = 64", name="content_hash_length"),
        CheckConstraint("char_length(deduplication_key) = 64", name="deduplication_key_length"),
        CheckConstraint(
            "total >= 0 AND valid >= 0 AND invalid >= 0 AND imported >= 0 "
            "AND duplicates >= 0 AND processed >= 0",
            name="counts_nonnegative",
        ),
    )
    initial_status = ImportStatus.PREPARED
    status: Mapped[ImportStatus] = state_column(ImportStatus, initial_status)
    integration_scope: Mapped[str] = mapped_column(String(128))
    creator_reference: Mapped[str] = mapped_column(String(160))
    freight_company_id: Mapped[UUID] = mapped_column()
    freight_location_id: Mapped[UUID | None] = mapped_column()
    filename: Mapped[str] = mapped_column(String(255))
    content_sha256: Mapped[str] = mapped_column(String(64))
    deduplication_key: Mapped[str] = mapped_column(String(64), unique=True)
    external_batch_id: Mapped[UUID | None] = mapped_column(active_history=True)
    external_status: Mapped[str | None] = mapped_column(String(80))
    external_dispatch_request_id: Mapped[str | None] = mapped_column(
        String(160), active_history=True
    )
    external_dispatch_status: Mapped[str | None] = mapped_column(String(80))
    total: Mapped[int] = mapped_column(default=0, server_default="0")
    valid: Mapped[int] = mapped_column(default=0, server_default="0")
    invalid: Mapped[int] = mapped_column(default=0, server_default="0")
    imported: Mapped[int] = mapped_column(default=0, server_default="0")
    duplicates: Mapped[int] = mapped_column(default=0, server_default="0")
    processed: Mapped[int] = mapped_column(default=0, server_default="0")


class Fulfillment(Stateful, MutableRecord, Base):
    __tablename__ = "fulfillments"
    __table_args__ = (
        UniqueConstraint("import_batch_id", "import_row_number"),
        CheckConstraint(
            "(import_batch_id IS NULL AND import_row_number IS NULL) OR "
            "(import_batch_id IS NOT NULL AND import_row_number IS NOT NULL "
            "AND import_row_number >= 1)",
            name="batch_row_pair",
        ),
        CheckConstraint(
            "imported_shipment_id IS NULL OR import_batch_id IS NOT NULL",
            name="native_shipment_has_batch",
        ),
    )
    initial_status = FulfillmentStatus.PAID_SIMULATED
    status: Mapped[FulfillmentStatus] = state_column(FulfillmentStatus, initial_status)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"), unique=True)
    import_batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("shipment_import_batches.id"), index=True
    )
    import_row_number: Mapped[int | None] = mapped_column(Integer)
    historical_shipment_id: Mapped[UUID | None] = mapped_column(index=True, active_history=True)
    imported_shipment_id: Mapped[str | None] = mapped_column(
        String(160), index=True, active_history=True
    )
    public_shipment_code: Mapped[str | None] = mapped_column(String(160))


class TrackingEvent(Record, Base):
    __tablename__ = "tracking_events"
    __table_args__ = (
        UniqueConstraint("fulfillment_id", "source", "event_key"),
        CheckConstraint("source IN ('simulated', 'packsenvios')", name="source_values"),
        Index("ix_tracking_events_fulfillment_time", "fulfillment_id", "occurred_at"),
    )
    fulfillment_id: Mapped[UUID] = mapped_column(ForeignKey("fulfillments.id"))
    source: Mapped[str] = mapped_column(String(16))
    event_key: Mapped[str] = mapped_column(String(160))
    external_event_id: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class IntegrationAudit(Record, Base):
    __tablename__ = "integration_audits"
    __table_args__ = (
        CheckConstraint("mode IN ('mock', 'real')", name="mode_values"),
        CheckConstraint(
            "outcome IN ('started', 'succeeded', 'failed', 'uncertain')", name="outcome_values"
        ),
        CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599", name="http_status_range"
        ),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_nonnegative"),
    )
    correlation_id: Mapped[UUID] = mapped_column(index=True)
    checkout_attempt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("checkout_attempts.id"), index=True
    )
    quote_id: Mapped[UUID | None] = mapped_column(ForeignKey("freight_quotes.id"), index=True)
    import_batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("shipment_import_batches.id"), index=True
    )
    operation: Mapped[str] = mapped_column(String(80))
    mode: Mapped[str] = mapped_column(String(8))
    outcome: Mapped[str] = mapped_column(String(16))
    request_key: Mapped[UUID | None] = mapped_column()
    http_status: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB)


class SnapshotImmutableError(ValueError):
    pass


@event.listens_for(Session, "before_flush")
def protect_snapshots(session, flush_context, instances):
    for entity in session.dirty:
        if isinstance(entity, (FreightOptionSnapshot, OrderItem)):
            if session.is_modified(entity, include_collections=False):
                raise SnapshotImmutableError("Persisted snapshot is immutable")
        frozen_fields = ()
        if isinstance(entity, FreightQuote):
            frozen_fields = ("criteria", "request_key", "integration_scope", "checkout_attempt_id")
        if isinstance(entity, Order):
            frozen_fields = (
                "submission_key",
                "checkout_attempt_id",
                "customer_id",
                "freight_quote_id",
                "freight_option_snapshot_id",
                "subtotal_cents",
                "freight_cents",
                "discount_cents",
                "total_cents",
                "simulation",
                "shipping_address_snapshot",
            )
        for field in frozen_fields:
            if inspect(entity).attrs[field].history.has_changes():
                raise SnapshotImmutableError(f"Persisted {field} is immutable")
        stable_ids = ()
        if isinstance(entity, FreightQuote):
            stable_ids = ("external_quote_request_id", "response")
        if isinstance(entity, ShipmentImportBatch):
            stable_ids = ("external_batch_id", "external_dispatch_request_id")
        if isinstance(entity, Fulfillment):
            stable_ids = ("historical_shipment_id", "imported_shipment_id")
        for field in stable_ids:
            history = inspect(entity).attrs[field].history
            if history.has_changes() and any(value is not None for value in history.deleted):
                raise SnapshotImmutableError(f"Persisted {field} cannot be replaced")
