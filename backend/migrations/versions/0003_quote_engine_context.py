"""Durable guest-cart requests, HTTP leases and local selection.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def quote_guard(new: bool) -> str:
    # Frozen migration SQL, not imported ORM models.
    added = (
        """
        OR (NEW.cart_id, NEW.prepared_payload, NEW.criteria_fingerprint, NEW.cart_fingerprint, NEW.mode)
        IS DISTINCT FROM
        (OLD.cart_id, OLD.prepared_payload, OLD.criteria_fingerprint, OLD.cart_fingerprint, OLD.mode)
    """
        if new
        else ""
    )
    checkout = (
        """(OLD.checkout_attempt_id IS NOT NULL AND
        NEW.checkout_attempt_id IS DISTINCT FROM OLD.checkout_attempt_id)"""
        if new
        else """
        NEW.checkout_attempt_id IS DISTINCT FROM OLD.checkout_attempt_id"""
    )
    return f"""
    CREATE OR REPLACE FUNCTION protect_checkout_snapshots() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_TABLE_NAME = 'orders' THEN
            IF (to_jsonb(NEW) - ARRAY['status', 'version', 'updated_at']) IS DISTINCT FROM
               (to_jsonb(OLD) - ARRAY['status', 'version', 'updated_at']) THEN
                RAISE EXCEPTION 'Order snapshot is immutable' USING ERRCODE = '23000';
            END IF;
        ELSE
            IF (NEW.criteria, NEW.request_key, NEW.integration_scope) IS DISTINCT FROM
               (OLD.criteria, OLD.request_key, OLD.integration_scope) OR {checkout}
               {added}
               OR (OLD.external_quote_request_id IS NOT NULL AND
                   NEW.external_quote_request_id IS DISTINCT FROM OLD.external_quote_request_id)
               OR (OLD.response IS NOT NULL AND NEW.response IS DISTINCT FROM OLD.response) THEN
                RAISE EXCEPTION 'Quote snapshot is immutable' USING ERRCODE = '23000';
            END IF;
        END IF;
        RETURN NEW;
    END;
    $$
    """


def upgrade() -> None:
    op.alter_column("freight_quotes", "checkout_attempt_id", nullable=True)
    for column in [
        sa.Column("cart_id", sa.Uuid(), nullable=True),
        sa.Column("prepared_payload", sa.LargeBinary(), nullable=True),
        sa.Column("criteria_fingerprint", sa.String(64), nullable=True),
        sa.Column("cart_fingerprint", sa.String(64), nullable=True),
        sa.Column("mode", sa.String(8), nullable=True),
        sa.Column("selected_option_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("inflight_token", sa.Uuid(), nullable=True),
        sa.Column("inflight_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("retry_not_before", sa.DateTime(timezone=True), nullable=True),
    ]:
        op.add_column("freight_quotes", column)
    op.create_foreign_key(
        op.f("fk_freight_quotes_cart_id_carts"), "freight_quotes", "carts", ["cart_id"], ["id"]
    )
    op.create_unique_constraint(
        "uq_checkout_attempts_id_cart", "checkout_attempts", ["id", "cart_id"]
    )
    op.create_foreign_key(
        "fk_freight_quotes_attempt_cart",
        "freight_quotes",
        "checkout_attempts",
        ["checkout_attempt_id", "cart_id"],
        ["id", "cart_id"],
    )
    op.create_index(op.f("ix_freight_quotes_cart_id"), "freight_quotes", ["cart_id"])
    op.create_index(
        "ix_freight_quotes_cart_criteria", "freight_quotes", ["cart_id", "criteria_fingerprint"]
    )
    op.create_check_constraint(
        op.f("ck_freight_quotes_mode_values"),
        "freight_quotes",
        "mode IS NULL OR mode IN ('mock', 'real')",
    )
    op.create_check_constraint(
        op.f("ck_freight_quotes_prepared_context"),
        "freight_quotes",
        "(prepared_payload IS NULL AND criteria_fingerprint IS NULL AND cart_fingerprint IS NULL AND mode IS NULL) OR "
        "(prepared_payload IS NOT NULL AND cart_id IS NOT NULL AND criteria_fingerprint IS NOT NULL "
        "AND cart_fingerprint IS NOT NULL AND char_length(criteria_fingerprint) = 64 "
        "AND char_length(cart_fingerprint) = 64 AND mode IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_freight_quotes_lease_pair"),
        "freight_quotes",
        "(inflight_token IS NULL AND inflight_until IS NULL) OR (inflight_token IS NOT NULL AND inflight_until IS NOT NULL)",
    )
    op.create_unique_constraint(
        "uq_freight_options_id_quote", "freight_option_snapshots", ["id", "quote_id"]
    )
    op.create_foreign_key(
        "fk_freight_quotes_local_selection",
        "freight_quotes",
        "freight_option_snapshots",
        ["selected_option_snapshot_id", "id"],
        ["id", "quote_id"],
    )
    op.alter_column("freight_option_snapshots", "carrier_name", type_=sa.Text(), nullable=True)
    op.alter_column("freight_option_snapshots", "manual_only", nullable=True)
    op.alter_column("freight_option_snapshots", "demonstration_only", nullable=True)
    op.execute(quote_guard(True))


def downgrade() -> None:
    # Restoring NOT NULL requires compatible data; never invent people, flags or carrier names.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM freight_quotes WHERE checkout_attempt_id IS NULL)
               OR EXISTS (SELECT 1 FROM freight_option_snapshots
                          WHERE carrier_name IS NULL OR char_length(carrier_name) > 160
                             OR manual_only IS NULL OR demonstration_only IS NULL) THEN
                RAISE EXCEPTION 'Downgrade 0003 requires legacy-compatible data; guest quotes or optional snapshots cannot be fabricated'
                    USING ERRCODE = '23514';
            END IF;
        END $$
    """)
    op.execute(quote_guard(False))
    op.drop_constraint("fk_freight_quotes_attempt_cart", "freight_quotes", type_="foreignkey")
    op.drop_constraint("uq_checkout_attempts_id_cart", "checkout_attempts", type_="unique")
    op.alter_column("freight_option_snapshots", "demonstration_only", nullable=False)
    op.alter_column("freight_option_snapshots", "manual_only", nullable=False)
    op.alter_column(
        "freight_option_snapshots", "carrier_name", type_=sa.String(160), nullable=False
    )
    op.drop_constraint("fk_freight_quotes_local_selection", "freight_quotes", type_="foreignkey")
    op.drop_constraint("uq_freight_options_id_quote", "freight_option_snapshots", type_="unique")
    op.drop_constraint(op.f("ck_freight_quotes_prepared_context"), "freight_quotes", type_="check")
    op.drop_constraint(op.f("ck_freight_quotes_lease_pair"), "freight_quotes", type_="check")
    op.drop_constraint(op.f("ck_freight_quotes_mode_values"), "freight_quotes", type_="check")
    op.drop_index("ix_freight_quotes_cart_criteria", table_name="freight_quotes")
    op.drop_index(op.f("ix_freight_quotes_cart_id"), table_name="freight_quotes")
    op.drop_constraint(
        op.f("fk_freight_quotes_cart_id_carts"), "freight_quotes", type_="foreignkey"
    )
    for column in [
        "retry_not_before",
        "last_error_code",
        "inflight_until",
        "inflight_token",
        "selected_option_snapshot_id",
        "mode",
        "cart_fingerprint",
        "criteria_fingerprint",
        "prepared_payload",
        "cart_id",
    ]:
        op.drop_column("freight_quotes", column)
    op.alter_column("freight_quotes", "checkout_attempt_id", nullable=False)
