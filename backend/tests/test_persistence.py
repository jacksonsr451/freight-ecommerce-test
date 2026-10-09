from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from alembic import command
from domain_fixtures import make_graph, make_product
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from freight_ecommerce.database import transaction
from freight_ecommerce.domain import models as m
from freight_ecommerce.domain.base import Base
from freight_ecommerce.domain.states import CartStatus

pytestmark = pytest.mark.postgres


def test_all_entities_roundtrip_uuid_utc_snapshots_and_distinct_external_ids(session):
    graph = make_graph(session)
    for table in Base.metadata.sorted_tables:
        assert session.scalar(select(func.count()).select_from(table)) == 1
    ids = {
        "request_key": graph.quote.request_key,
        "quote_resource": graph.quote.external_quote_request_id,
        "batch_resource": graph.batch.external_batch_id,
        "historical_shipment": graph.fulfillment.historical_shipment_id,
        "native_imported_shipment": graph.fulfillment.imported_shipment_id,
    }
    payload = deepcopy(graph.option.payload)
    graph.product.price_cents = 99999
    graph.address.street = "Endereço alterado no cadastro"
    session.commit()
    session.expire_all()
    assert graph.option.payload == payload
    assert graph.line.unit_price_cents == 10000
    assert graph.order.shipping_address_snapshot["postal_code"] == "01001000"
    assert graph.quote.request_key == ids["request_key"]
    assert graph.quote.external_quote_request_id == ids["quote_resource"]
    assert graph.batch.external_batch_id == ids["batch_resource"]
    assert graph.fulfillment.historical_shipment_id == ids["historical_shipment"]
    assert graph.fulfillment.imported_shipment_id == ids["native_imported_shipment"]
    assert graph.order.created_at.utcoffset() == timedelta(0)
    assert graph.tracking.occurred_at == datetime(2026, 10, 8, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "kind",
    [
        "negative_price",
        "reserved_exceeds_stock",
        "negative_stock",
        "zero_quantity",
        "missing_product",
        "duplicate_sku",
        "duplicate_cart_product",
        "duplicate_normalized_email",
    ],
)
def test_database_constraints_and_uniqueness(session, kind):
    product = make_product()
    cart = m.Cart()
    session.add_all([product, cart])
    session.flush()
    session.add(m.CartItem(cart_id=cart.id, product_id=product.id, quantity=1))
    session.add(m.Customer(name="Synthetic", email="synthetic@example.test"))
    session.commit()
    invalid = {
        "negative_price": lambda: make_product(price_cents=-1),
        "reserved_exceeds_stock": lambda: m.Inventory(product_id=product.id, on_hand=1, reserved=2),
        "negative_stock": lambda: m.Inventory(product_id=product.id, on_hand=-1),
        "zero_quantity": lambda: m.CartItem(cart_id=cart.id, product_id=product.id, quantity=0),
        "missing_product": lambda: m.Inventory(product_id=uuid4(), on_hand=1),
        "duplicate_sku": lambda: make_product(sku=product.sku),
        "duplicate_cart_product": lambda: m.CartItem(
            cart_id=cart.id, product_id=product.id, quantity=1
        ),
        "duplicate_normalized_email": lambda: m.Customer(
            name="Synthetic", email="SYNTHETIC@example.test"
        ),
    }[kind]()
    session.add(invalid)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    assert session.get(m.Product, product.id) is not None


def test_checkout_address_must_belong_to_customer(session):
    graph = make_graph(session)
    other = m.Customer(name="Outro sintético", email=f"{uuid4().hex}@example.test")
    session.add(other)
    session.flush()
    session.add(
        m.CheckoutAttempt(
            cart_id=graph.cart.id,
            customer_id=other.id,
            address_id=graph.address.id,
            cart_revision=1,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_request_key_is_unique_per_local_organization_namespace(session):
    graph = make_graph(session)
    values = {
        "checkout_attempt_id": graph.checkout.id,
        "request_key": graph.quote.request_key,
        "criteria": deepcopy(graph.quote.criteria),
    }
    session.add(m.FreightQuote(integration_scope=graph.quote.integration_scope, **values))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    other_scope = m.FreightQuote(integration_scope="another-synthetic-organization", **values)
    session.add(other_scope)
    session.commit()
    assert other_scope.id != graph.quote.id


def test_option_identity_is_snapshot_and_index_not_rate_table(session):
    graph = make_graph(session)
    table_id = str(uuid4())
    for index in (1, 2):
        session.add(
            m.FreightOptionSnapshot(
                quote_id=graph.quote.id,
                option_index=index,
                price_cents=2590,
                deadline_days=3,
                carrier_name="Synthetic",
                manual_only=True,
                demonstration_only=True,
                weight_only=False,
                payload={"synthetic_fixture": True, "rate_table_id": table_id},
            )
        )
    session.commit()
    options = session.scalars(select(m.FreightOptionSnapshot)).all()
    assert len({option.id for option in options}) == 3
    session.add(
        m.FreightOptionSnapshot(
            quote_id=graph.quote.id,
            option_index=1,
            price_cents=2590,
            deadline_days=3,
            carrier_name="Synthetic",
            manual_only=True,
            demonstration_only=True,
            weight_only=False,
            payload={"synthetic_fixture": True},
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_order_insert_rejects_an_option_from_another_quote(session):
    graph = make_graph(session)
    checkout = m.CheckoutAttempt(
        cart_id=graph.cart.id,
        customer_id=graph.customer.id,
        address_id=graph.address.id,
        cart_revision=1,
    )
    session.add(checkout)
    session.flush()
    quote = m.FreightQuote(
        checkout_attempt_id=checkout.id,
        request_key=uuid4(),
        integration_scope="synthetic",
        criteria={"synthetic_fixture": True},
    )
    session.add(quote)
    session.flush()
    session.add(
        m.Order(
            checkout_attempt_id=checkout.id,
            submission_key=uuid4(),
            customer_id=graph.customer.id,
            freight_quote_id=quote.id,
            freight_option_snapshot_id=graph.option.id,
            subtotal_cents=10000,
            freight_cents=2590,
            total_cents=12590,
            shipping_address_snapshot={"synthetic_fixture": True},
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_import_batch_deduplication_key_is_unique(session):
    graph = make_graph(session)
    session.add(
        m.ShipmentImportBatch(
            integration_scope=graph.batch.integration_scope,
            creator_reference=graph.batch.creator_reference,
            freight_company_id=graph.batch.freight_company_id,
            filename="duplicate-synthetic.csv",
            content_sha256=graph.batch.content_sha256,
            deduplication_key=graph.batch.deduplication_key,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


@pytest.mark.parametrize("kind", ["price", "quote", "payment", "batch_row", "simulation", "state"])
def test_server_snapshots_and_resource_links_cannot_be_tampered_in_sql(session, kind):
    graph = make_graph(session)
    statement = {
        "price": update(m.Order)
        .where(m.Order.id == graph.order.id)
        .values(freight_cents=2591, total_cents=12591),
        "quote": update(m.Order)
        .where(m.Order.id == graph.order.id)
        .values(freight_quote_id=uuid4()),
        "payment": update(m.PaymentSimulation)
        .where(m.PaymentSimulation.id == graph.payment.id)
        .values(amount_cents=1),
        "batch_row": update(m.Fulfillment)
        .where(m.Fulfillment.id == graph.fulfillment.id)
        .values(import_row_number=None),
        "simulation": update(m.PaymentSimulation)
        .where(m.PaymentSimulation.id == graph.payment.id)
        .values(simulation=False),
        "state": update(m.Cart).where(m.Cart.id == graph.cart.id).values(status="invented_state"),
    }[kind]
    with pytest.raises(IntegrityError):
        session.execute(statement)
    session.rollback()


def test_orm_and_database_protect_immutable_option_and_order_item(session):
    graph = make_graph(session)
    original = deepcopy(graph.option.payload)
    graph.option.price_cents = 1
    with pytest.raises(m.SnapshotImmutableError):
        session.flush()
    session.rollback()
    for entity, field, value in [
        (m.FreightOptionSnapshot, "payload", {"synthetic_fixture": True, "tampered": True}),
        (m.OrderItem, "name", "tampered"),
    ]:
        with pytest.raises(IntegrityError, match="snapshot is immutable"):
            session.execute(update(entity).values(**{field: value}))
        session.rollback()
    session.expire_all()
    assert graph.option.payload == original


def test_quote_criteria_and_external_identity_cannot_be_replaced(session):
    graph = make_graph(session)
    for field, value in [
        ("request_key", uuid4()),
        ("criteria", {"weight_kg": "2.000"}),
        ("external_quote_request_id", uuid4()),
    ]:
        setattr(graph.quote, field, value)
        with pytest.raises(m.SnapshotImmutableError):
            session.flush()
        session.rollback()


def test_transaction_rolls_back_stock_and_failed_insert_together(session, db_engine):
    graph = make_graph(session)
    with pytest.raises(IntegrityError), transaction(db_engine) as tx:
        stock = tx.get(m.Inventory, graph.inventory.id)
        stock.reserved = 2
        tx.add(m.CartItem(cart_id=graph.cart.id, product_id=graph.product.id, quantity=0))
        tx.flush()
    session.expire_all()
    assert graph.inventory.reserved == 0
    assert session.scalar(select(func.count()).select_from(m.CartItem)) == 1


def test_concurrent_state_updates_reject_lost_update(session, db_engine):
    cart = m.Cart()
    session.add(cart)
    session.commit()
    with Session(db_engine) as first, Session(db_engine) as second:
        a = first.get(m.Cart, cart.id)
        b = second.get(m.Cart, cart.id)
        a.transition(CartStatus.CHECKOUT_PENDING)
        first.commit()
        b.transition(CartStatus.ABANDONED)
        with pytest.raises(StaleDataError):
            second.commit()
        second.rollback()
    session.expire_all()
    assert cart.status == CartStatus.CHECKOUT_PENDING


def test_utc_persistence_rejects_naive_timestamp_and_preserves_instant(session):
    graph = make_graph(session)
    event = m.TrackingEvent(
        fulfillment_id=graph.fulfillment.id,
        source="simulated",
        event_key="offset-event",
        status="simulado",
        title="Synthetic",
        payload={"synthetic_fixture": True},
        occurred_at=datetime(2026, 10, 8, 9),
    )
    session.add(event)
    with pytest.raises(StatementError, match="timezone-aware"):
        session.flush()
    session.rollback()
    event.occurred_at = datetime(2026, 10, 8, 9, tzinfo=timezone(timedelta(hours=-3)))
    session.add(event)
    session.commit()
    session.expire_all()
    assert event.occurred_at == datetime(2026, 10, 8, 12, tzinfo=UTC)


def test_migration_downgrade_upgrade_and_metadata_have_no_drift(db_engine, alembic_config):
    with db_engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
        connection.commit()
        config = alembic_config(connection, schema)
        command.check(config)
        connection.commit()
        command.downgrade(config, "base")
        connection.commit()
        assert inspect(connection).get_table_names() == ["alembic_version"]
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_proc WHERE pronamespace = "
                    "(SELECT oid FROM pg_namespace WHERE nspname = :schema) "
                    "AND proname = 'reject_snapshot_update'"
                ),
                {"schema": schema},
            )
            == 0
        )
        connection.commit()
        command.upgrade(config, "head")
        connection.commit()
        assert set(inspect(connection).get_table_names()) == set(Base.metadata.tables) | {
            "alembic_version"
        }
        command.check(config)
        connection.commit()
