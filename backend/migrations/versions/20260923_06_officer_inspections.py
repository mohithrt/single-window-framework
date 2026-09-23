"""Add scheduled single and joint inspections for officer review."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260923_06"
down_revision: str | None = "20260923_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inspections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("approval_id", sa.Integer(), nullable=False),
        sa.Column("inspection_type", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="SCHEDULED", nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(length=500), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("scheduled_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("inspection_type IN ('SINGLE', 'JOINT')", name="ck_inspections_type"),
        sa.CheckConstraint("status IN ('SCHEDULED', 'COMPLETED', 'CANCELLED')", name="ck_inspections_status"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_id"], ["application_approvals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scheduled_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_inspections_scheduled_type", "inspections", ["scheduled_at", "inspection_type"])
    op.create_index("ix_inspections_application_status", "inspections", ["application_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_inspections_application_status", table_name="inspections")
    op.drop_index("ix_inspections_scheduled_type", table_name="inspections")
    op.drop_table("inspections")
