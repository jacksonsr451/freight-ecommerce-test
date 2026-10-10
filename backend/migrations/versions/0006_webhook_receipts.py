"""Store signed webhook receipts for later authorized reconciliation.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_receipts",
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("delivery_id", sa.Text(), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=True),
        sa.Column("shipment_id", sa.Text(), nullable=True),
        sa.Column("public_code", sa.Text(), nullable=True),
        sa.Column("dispatch_status", sa.Text(), nullable=True),
        sa.Column("body_sha256", sa.String(length=64), nullable=False),
        sa.Column("out_of_order", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "reconciliation_status",
            sa.String(length=32),
            server_default="reconciliation_pending",
            nullable=False,
        ),
        sa.Column(
            "worker_status", sa.String(length=20), server_default="not_configured", nullable=False
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(body_sha256) = 64",
            name=op.f("ck_webhook_receipts_body_hash_length"),
        ),
        sa.CheckConstraint(
            "reconciliation_status IN ('reconciliation_pending', 'reconciled')",
            name=op.f("ck_webhook_receipts_reconciliation_status_values"),
        ),
        sa.CheckConstraint(
            "worker_status IN ('not_configured', 'notified', 'unavailable')",
            name=op.f("ck_webhook_receipts_worker_status_values"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name=op.f("ck_webhook_receipts_payload_object"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_receipts")),
        sa.UniqueConstraint("event_id", name=op.f("uq_webhook_receipts_event_id")),
    )
    op.create_index(
        "ix_webhook_receipts_company_shipment_occurred",
        "webhook_receipts",
        ["company_id", "location_id", "shipment_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM webhook_receipts) THEN
                RAISE EXCEPTION 'Downgrade 0006 is blocked while webhook receipts exist'
                    USING ERRCODE = '23514';
            END IF;
        END $$
        """
    )
    op.drop_index("ix_webhook_receipts_company_shipment_occurred", table_name="webhook_receipts")
    op.drop_table("webhook_receipts")
