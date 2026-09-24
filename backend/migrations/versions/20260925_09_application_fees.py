"""Add application fee ledger entries for transparency and demo fixtures."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260925_09"
down_revision: str | None = "20260924_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_fees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fee_code", sa.String(40), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="INR", nullable=False),
        sa.Column("status", sa.String(16), server_default="ESTIMATED", nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True)),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("receipt_reference", sa.String(64), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("application_id", "fee_code", name="uq_application_fees_code"),
        sa.CheckConstraint("amount >= 0", name="ck_application_fees_amount"),
        sa.CheckConstraint("status IN ('ESTIMATED', 'DUE', 'PAID', 'WAIVED')", name="ck_application_fees_status"),
    )
    op.create_index("ix_application_fees_application_status", "application_fees", ["application_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_application_fees_application_status", table_name="application_fees")
    op.drop_table("application_fees")
