"""Create applicant applications and document metadata.

Revision ID: 20260923_02
Revises: 20260923_01
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260923_02"
down_revision: str | None = "20260923_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_number", sa.String(length=32), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("current_department_id", sa.Integer(), nullable=True),
        sa.Column("applicant_name", sa.String(length=160), nullable=True),
        sa.Column("applicant_email", sa.String(length=254), nullable=True),
        sa.Column("applicant_phone", sa.String(length=30), nullable=True),
        sa.Column("company_name", sa.String(length=200), nullable=True),
        sa.Column("pan", sa.String(length=10), nullable=True),
        sa.Column("gstin", sa.String(length=15), nullable=True),
        sa.Column("cin", sa.String(length=21), nullable=True),
        sa.Column("udyam_number", sa.String(length=30), nullable=True),
        sa.Column("industry_type", sa.String(length=40), nullable=True),
        sa.Column("other_industry_name", sa.String(length=120), nullable=True),
        sa.Column("project_type", sa.String(length=100), nullable=True),
        sa.Column("project_description", sa.String(length=5000), nullable=True),
        sa.Column("investment_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("number_of_employees", sa.Integer(), nullable=True),
        sa.Column("built_up_area", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("power_requirement", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("water_requirement", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("project_location", sa.String(length=500), nullable=True),
        sa.Column("land_details", sa.String(length=3000), nullable=True),
        sa.Column("midc_area", sa.Boolean(), nullable=True),
        sa.Column("midc_area_name", sa.String(length=160), nullable=True),
        sa.Column("pollution_category", sa.String(length=24), nullable=True),
        sa.Column("hazardous_materials", sa.Boolean(), nullable=True),
        sa.Column("hazardous_materials_details", sa.String(length=3000), nullable=True),
        sa.Column("factory_information", sa.String(length=3000), nullable=True),
        sa.Column("fire_safety_information", sa.String(length=3000), nullable=True),
        sa.Column("risk_tier", sa.String(length=24), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="DRAFT", nullable=False),
        sa.Column("progress_percent", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expected_completion_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'SUBMITTED', 'IN_REVIEW', 'ACTION_REQUIRED', 'APPROVED', 'REJECTED')",
            name="ck_applications_status",
        ),
        sa.CheckConstraint("progress_percent BETWEEN 0 AND 100", name="ck_applications_progress"),
        sa.CheckConstraint(
            "industry_type IS NULL OR industry_type IN ('IT / Software', 'Manufacturing', 'Food Processing', 'Textile', 'Chemical', 'Pharmaceutical', 'Automobile', 'Electronics', 'Logistics', 'Other')",
            name="ck_applications_industry_type",
        ),
        sa.CheckConstraint(
            "pollution_category IS NULL OR pollution_category IN ('White', 'Green', 'Orange', 'Red', 'Not sure')",
            name="ck_applications_pollution_category",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["current_department_id"], ["departments.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_applications_application_number", "applications", ["application_number"], unique=True)
    op.create_index("ix_applications_owner_user_id", "applications", ["owner_user_id"], unique=False)
    op.create_index("ix_applications_company_id", "applications", ["company_id"], unique=False)
    op.create_index("ix_applications_status", "applications", ["status"], unique=False)
    op.create_index("ix_applications_owner_status", "applications", ["owner_user_id", "status"], unique=False)

    op.create_table(
        "application_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=40), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("storage_key", name="uq_application_documents_storage_key"),
    )
    op.create_index("ix_application_documents_application", "application_documents", ["application_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_application_documents_application", table_name="application_documents")
    op.drop_table("application_documents")
    op.drop_index("ix_applications_owner_status", table_name="applications")
    op.drop_index("ix_applications_status", table_name="applications")
    op.drop_index("ix_applications_company_id", table_name="applications")
    op.drop_index("ix_applications_owner_user_id", table_name="applications")
    op.drop_index("ix_applications_application_number", table_name="applications")
    op.drop_table("applications")
