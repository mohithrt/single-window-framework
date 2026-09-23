"""Add secure document processing metadata and pre-validation findings.

Revision ID: 20260923_03
Revises: 20260923_02
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260923_03"
down_revision: str | None = "20260923_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE application_documents SET document_type = 'LAND_OWNERSHIP_LEASE' WHERE document_type = 'LAND_DOCUMENT'")
    op.execute("UPDATE application_documents SET document_type = 'BUILDING_PLAN' WHERE document_type = 'SITE_PLAN'")
    op.execute("UPDATE application_documents SET document_type = 'OTHER_SUPPORTING' WHERE document_type = 'OTHER'")
    op.add_column("application_documents", sa.Column("sha256", sa.String(length=64), nullable=False, server_default=""))
    op.add_column("application_documents", sa.Column("status", sa.String(length=24), nullable=False, server_default="PROCESSING"))
    op.add_column("application_documents", sa.Column("extracted_text", sa.Text(), nullable=True))
    op.add_column("application_documents", sa.Column("extracted_fields", sa.JSON(), nullable=True))
    op.add_column("application_documents", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_application_documents_sha256", "application_documents", ["sha256"])
    op.create_table(
        "application_validation_issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("document_type", sa.String(length=40), nullable=False),
        sa.Column("code", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("detected_value", sa.String(length=255), nullable=True),
        sa.Column("expected_value", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["application_documents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_validation_issues_application_status", "application_validation_issues", ["application_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_validation_issues_application_status", table_name="application_validation_issues")
    op.drop_table("application_validation_issues")
    op.drop_index("ix_application_documents_sha256", table_name="application_documents")
    op.drop_column("application_documents", "processed_at")
    op.drop_column("application_documents", "extracted_fields")
    op.drop_column("application_documents", "extracted_text")
    op.drop_column("application_documents", "status")
    op.drop_column("application_documents", "sha256")
