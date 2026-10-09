"""Persist the guest cart destination and server-side commercial fingerprint.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "carts", sa.Column("delivery_address", postgresql.JSONB(none_as_null=True), nullable=True)
    )
    op.add_column("carts", sa.Column("commercial_fingerprint", sa.String(64), nullable=True))
    op.create_check_constraint(
        op.f("ck_carts_delivery_address_object"),
        "carts",
        "delivery_address IS NULL OR jsonb_typeof(delivery_address) = 'object'",
    )
    op.create_check_constraint(
        op.f("ck_carts_commercial_fingerprint_length"),
        "carts",
        "commercial_fingerprint IS NULL OR char_length(commercial_fingerprint) = 64",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_carts_commercial_fingerprint_length"), "carts", type_="check")
    op.drop_constraint(op.f("ck_carts_delivery_address_object"), "carts", type_="check")
    op.drop_column("carts", "commercial_fingerprint")
    op.drop_column("carts", "delivery_address")
