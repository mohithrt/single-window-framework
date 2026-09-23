"""Add configurable application approval workflow and audit events.

Revision ID: 20260923_05
Revises: 20260923_04
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260923_05"
down_revision: str | None = "20260923_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


APPROVAL_STATUSES = "'NOT_STARTED', 'PENDING', 'IN_REVIEW', 'DOCUMENT_CORRECTION', 'INSPECTION_REQUIRED', 'APPROVED', 'REJECTED', 'ESCALATED'"


def upgrade() -> None:
    op.create_table(
        "application_approvals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("department_code", sa.String(length=24), nullable=False),
        sa.Column("department_name", sa.String(length=80), nullable=False),
        sa.Column("is_required", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="NOT_STARTED", nullable=False),
        sa.Column("depends_on", sa.JSON(), nullable=False),
        sa.Column("decision_message", sa.Text(), nullable=True),
        sa.Column("assigned_reviewer_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"status IN ({APPROVAL_STATUSES})", name="ck_application_approvals_status"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("application_id", "department_code", name="uq_application_approval_department"),
    )
    op.create_index("ix_application_approvals_application_status", "application_approvals", ["application_id", "status"])
    op.create_table(
        "workflow_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("approval_id", sa.Integer(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_id"], ["application_approvals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_workflow_events_application_created", "workflow_audit_events", ["application_id", "created_at"])
    op.create_index("ix_workflow_events_approval", "workflow_audit_events", ["approval_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_events_approval", table_name="workflow_audit_events")
    op.drop_index("ix_workflow_events_application_created", table_name="workflow_audit_events")
    op.drop_table("workflow_audit_events")
    op.drop_index("ix_application_approvals_application_status", table_name="application_approvals")
    op.drop_table("application_approvals")
