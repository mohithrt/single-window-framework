"""Store transparent risk assessment history.

Revision ID: 20260923_04
Revises: 20260923_03
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260923_04"
down_revision: str | None = "20260923_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("assessed_by_user_id", sa.Integer(), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("risk_tier", sa.String(length=16), nullable=False),
        sa.Column("rules_version", sa.String(length=32), nullable=False),
        sa.Column("assessment_data", sa.JSON(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("rules_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_risk_assessments_score"),
        sa.CheckConstraint("risk_tier IN ('LOW', 'MEDIUM', 'HIGH')", name="ck_risk_assessments_tier"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assessed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_risk_assessments_application_created",
        "risk_assessments",
        ["application_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_risk_assessments_application_created", table_name="risk_assessments")
    op.drop_table("risk_assessments")
