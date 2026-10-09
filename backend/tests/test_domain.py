from datetime import UTC, datetime, timedelta, timezone
from io import StringIO

import pytest
from alembic import command

from freight_ecommerce.domain.base import UTCDateTime
from freight_ecommerce.domain.models import (
    Cart,
    CheckoutAttempt,
    FreightOptionSnapshot,
    FreightQuote,
    Fulfillment,
    Order,
    PaymentSimulation,
    ShipmentImportBatch,
)
from freight_ecommerce.domain.states import (
    CartStatus,
    CheckoutStatus,
    FulfillmentStatus,
    ImportStatus,
    OrderStatus,
    PaymentStatus,
    QuoteStatus,
    TransitionError,
)


@pytest.mark.parametrize(
    "entity,target",
    [
        (Cart(), CartStatus.CHECKED_OUT),
        (CheckoutAttempt(), CheckoutStatus.CONFIRMED),
        (FreightQuote(status=QuoteStatus.INVALIDATED), QuoteStatus.RECEIVED),
        (Order(status=OrderStatus.CANCELLED), OrderStatus.PAID_SIMULATED),
        (PaymentSimulation(status=PaymentStatus.APPROVED), PaymentStatus.PENDING),
        (Fulfillment(), FulfillmentStatus.DELIVERED_SIMULATED),
        (ShipmentImportBatch(), ImportStatus.COMPLETED),
    ],
)
def test_invalid_local_transitions_are_rejected(entity, target):
    with pytest.raises(TransitionError, match="Invalid local transition"):
        entity.transition(target)


def test_direct_assignment_cannot_bypass_graph_and_other_lifecycle_is_rejected():
    cart = Cart()
    with pytest.raises(TransitionError):
        cart.status = "checked_out"
    with pytest.raises(TransitionError, match="another lifecycle"):
        cart.transition(PaymentStatus.PENDING)
    cart.transition(CartStatus.CHECKOUT_PENDING)
    cart.transition(CartStatus.CHECKOUT_PENDING)  # idempotent local operation
    cart.transition(CartStatus.CHECKED_OUT)
    with pytest.raises(TransitionError):
        cart.transition(CartStatus.ACTIVE)


@pytest.mark.parametrize(
    "flags",
    [
        {"manual_only": True},
        {"demonstration_only": True},
        {"weight_only": True},
    ],
)
def test_estimates_or_manual_offers_never_enable_automatic_contract(flags):
    option = FreightOptionSnapshot(
        manual_only=False,
        demonstration_only=False,
        weight_only=False,
    )
    for key, value in flags.items():
        setattr(option, key, value)
    with pytest.raises(ValueError, match="not eligible"):
        option.require_automatic_contract_eligibility()
    eligible_flags = FreightOptionSnapshot(
        manual_only=False,
        demonstration_only=False,
        weight_only=False,
    )
    with pytest.raises(NotImplementedError, match="TODO-CONTRACT"):
        eligible_flags.require_automatic_contract_eligibility()


def test_utc_type_rejects_naive_and_canonicalizes_offset():
    type_ = UTCDateTime()
    with pytest.raises(ValueError, match="timezone-aware"):
        type_.process_bind_param(datetime(2026, 10, 8), None)
    source = datetime(2026, 10, 8, 9, tzinfo=timezone(timedelta(hours=-3)))
    assert type_.process_bind_param(source, None) == datetime(2026, 10, 8, 12, tzinfo=UTC)


def test_postgres_offline_migrations_generate_upgrade_and_downgrade(alembic_config):
    upgrade = StringIO()
    config = alembic_config()
    config.output_buffer = upgrade
    command.upgrade(config, "head", sql=True)
    sql = upgrade.getvalue()
    assert sql.count("CREATE TABLE ") == 17  # 16 entities + Alembic version
    assert "JSONB" in sql and "UUID" in sql and "TIMESTAMP WITH TIME ZONE" in sql
    assert "CREATE TRIGGER" in sql
    downgrade = StringIO()
    config.output_buffer = downgrade
    command.downgrade(config, "0003:base", sql=True)
    assert downgrade.getvalue().count("DROP TABLE ") == 16  # version table is retained by Alembic
    assert "DROP FUNCTION" in downgrade.getvalue()
    assert "DROP COLUMN delivery_address" in downgrade.getvalue()
