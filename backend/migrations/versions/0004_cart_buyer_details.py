"""Local buyer details without fabricating or claiming a customer account.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "carts", sa.Column("buyer_details", postgresql.JSONB(none_as_null=True), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_carts_buyer_details_object"),
        "carts",
        "buyer_details IS NULL OR jsonb_typeof(buyer_details) = 'object'",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_carts_buyer_details_object"), "carts", type_="check")
    op.drop_column("carts", "buyer_details")
