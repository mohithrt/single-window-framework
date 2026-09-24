"""Extend inspections and add participant, SLA, and notification records."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260924_07"
down_revision: str | None = "20260923_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "joint_inspections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("site", sa.String(length=500), nullable=False),
        sa.Column("instructions", sa.Text()),
        sa.Column("status", sa.String(length=16), server_default="SCHEDULED", nullable=False),
        sa.Column("checklist", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("findings", sa.Text()),
        sa.Column("photos", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("remarks", sa.Text()),
        sa.Column("recommendation", sa.Text()),
        sa.Column("scheduled_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('SCHEDULED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')", name="ck_joint_inspections_status"),
    )
    op.create_index("ix_joint_inspections_application_date", "joint_inspections", ["application_id", "scheduled_at"])

    with op.batch_alter_table("inspections") as batch:
        batch.drop_constraint("ck_inspections_status", type_="check")
        batch.create_check_constraint("ck_inspections_status", "status IN ('SCHEDULED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')")
        batch.add_column(sa.Column("updated_by_user_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("joint_inspection_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("site", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("checklist", sa.JSON(), server_default="[]", nullable=False))
        batch.add_column(sa.Column("findings", sa.Text(), nullable=True))
        batch.add_column(sa.Column("photos", sa.JSON(), server_default="[]", nullable=False))
        batch.add_column(sa.Column("remarks", sa.Text(), nullable=True))
        batch.add_column(sa.Column("recommendation", sa.Text(), nullable=True))
        batch.create_foreign_key("fk_inspections_updated_by_user_id_users", "users", ["updated_by_user_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_inspections_joint_inspection_id_joint_inspections", "joint_inspections", ["joint_inspection_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_inspections_joint_inspection_id", "inspections", ["joint_inspection_id"])

    op.create_table(
        "inspection_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("joint_inspection_id", sa.Integer(), sa.ForeignKey("joint_inspections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("approval_id", sa.Integer(), sa.ForeignKey("application_approvals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("officer_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(length=16), server_default="INVITED", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("joint_inspection_id", "approval_id", name="uq_inspection_participant_approval"),
    )
    op.create_index("ix_inspection_participants_officer", "inspection_participants", ["officer_user_id"])

    with op.batch_alter_table("application_approvals") as batch:
        batch.add_column(sa.Column("sla_started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("sla_duration_days", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("sla_expected_completion", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("workflow_audit_events", sa.Column("department_code", sa.String(length=24), nullable=True))
    op.create_index("ix_workflow_audit_events_department_code", "workflow_audit_events", ["department_code"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id", ondelete="CASCADE")),
        sa.Column("notification_type", sa.String(length=40), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_notifications_user_read_created", "notifications", ["user_id", "is_read", "created_at"])
    op.create_index("ix_notifications_application", "notifications", ["application_id"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_index("ix_workflow_audit_events_department_code", table_name="workflow_audit_events")
    op.drop_column("workflow_audit_events", "department_code")
    with op.batch_alter_table("application_approvals") as batch:
        batch.drop_column("escalated_at")
        batch.drop_column("sla_expected_completion")
        batch.drop_column("sla_duration_days")
        batch.drop_column("sla_started_at")
    op.drop_index("ix_inspection_participants_officer", table_name="inspection_participants")
    op.drop_table("inspection_participants")
    op.drop_index("ix_inspections_joint_inspection_id", table_name="inspections")
    with op.batch_alter_table("inspections") as batch:
        batch.drop_constraint("fk_inspections_joint_inspection_id_joint_inspections", type_="foreignkey")
        batch.drop_constraint("fk_inspections_updated_by_user_id_users", type_="foreignkey")
        batch.drop_column("recommendation")
        batch.drop_column("remarks")
        batch.drop_column("photos")
        batch.drop_column("findings")
        batch.drop_column("checklist")
        batch.drop_column("site")
        batch.drop_column("joint_inspection_id")
        batch.drop_column("updated_by_user_id")
        batch.drop_constraint("ck_inspections_status", type_="check")
        batch.create_check_constraint("ck_inspections_status", "status IN ('SCHEDULED', 'COMPLETED', 'CANCELLED')")
    op.drop_index("ix_joint_inspections_application_date", table_name="joint_inspections")
    op.drop_table("joint_inspections")
