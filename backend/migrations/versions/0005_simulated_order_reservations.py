"""Persist local order revision/idempotency evidence and compensatable stock reservations.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("cart_revision", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("submission_fingerprint", sa.String(64), nullable=True))
    op.add_column("orders", sa.Column("cart_fingerprint", sa.String(64), nullable=True))
    op.create_check_constraint(
        op.f("ck_orders_cart_revision_positive"),
        "orders",
        "cart_revision IS NULL OR cart_revision > 0",
    )
    op.create_check_constraint(
        op.f("ck_orders_submission_fingerprint_length"),
        "orders",
        "submission_fingerprint IS NULL OR char_length(submission_fingerprint) = 64",
    )
    op.create_check_constraint(
        op.f("ck_orders_cart_fingerprint_length"),
        "orders",
        "cart_fingerprint IS NULL OR char_length(cart_fingerprint) = 64",
    )
    op.create_unique_constraint(
        "uq_payment_simulations_order_id", "payment_simulations", ["order_id"]
    )
    op.create_table(
        "stock_reservations",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_stock_reservations_quantity_positive")),
        sa.CheckConstraint(
            "(active AND released_at IS NULL) OR (NOT active AND released_at IS NOT NULL)",
            name=op.f("ck_stock_reservations_release_timestamp_pair"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name=op.f("fk_stock_reservations_order_id_orders")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_stock_reservations_product_id_products")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_reservations")),
        sa.UniqueConstraint("order_id", "product_id", name=op.f("uq_stock_reservations_order_id")),
    )
    op.create_index(op.f("ix_stock_reservations_order_id"), "stock_reservations", ["order_id"])
    op.create_index(op.f("ix_stock_reservations_product_id"), "stock_reservations", ["product_id"])


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM orders)
               OR EXISTS (SELECT 1 FROM payment_simulations)
               OR EXISTS (SELECT 1 FROM stock_reservations) THEN
                RAISE EXCEPTION 'Downgrade 0005 is blocked while local order/payment/reservation records exist'
                    USING ERRCODE = '23514';
            END IF;
        END $$
    """)
    op.drop_index(op.f("ix_stock_reservations_product_id"), table_name="stock_reservations")
    op.drop_index(op.f("ix_stock_reservations_order_id"), table_name="stock_reservations")
    op.drop_table("stock_reservations")
    op.drop_constraint("uq_payment_simulations_order_id", "payment_simulations", type_="unique")
    op.drop_constraint(op.f("ck_orders_cart_fingerprint_length"), "orders", type_="check")
    op.drop_constraint(op.f("ck_orders_submission_fingerprint_length"), "orders", type_="check")
    op.drop_constraint(op.f("ck_orders_cart_revision_positive"), "orders", type_="check")
    op.drop_column("orders", "submission_fingerprint")
    op.drop_column("orders", "cart_fingerprint")
    op.drop_column("orders", "cart_revision")
