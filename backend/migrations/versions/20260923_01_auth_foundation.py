"""Create users, roles, companies, and departments.

Revision ID: 20260923_01
Revises:
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260923_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=24), nullable=False),
        sa.Column("description", sa.String(length=160), nullable=False),
        sa.CheckConstraint("code IN ('APPLICANT', 'OFFICER', 'ADMIN')", name="ck_roles_code"),
    )
    op.create_index("ix_roles_code", "roles", ["code"], unique=True)

    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("registration_number", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("registration_number", name="uq_companies_registration_number"),
    )
    op.create_index("ix_companies_name", "companies", ["name"], unique=False)

    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("company_id", "code", name="uq_departments_company_code"),
    )
    op.create_index("ix_departments_company_id", "departments", ["company_id"], unique=False)
    op.create_index("ix_departments_company_name", "departments", ["company_id", "name"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(password_hash) > 0", name="ck_users_password_hash_nonempty"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role_id", "users", ["role_id"], unique=False)
    op.create_index("ix_users_company_id", "users", ["company_id"], unique=False)
    op.create_index("ix_users_department_id", "users", ["department_id"], unique=False)
    op.create_index("ix_users_role_active", "users", ["role_id", "is_active"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_role_active", table_name="users")
    op.drop_index("ix_users_department_id", table_name="users")
    op.drop_index("ix_users_company_id", table_name="users")
    op.drop_index("ix_users_role_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_departments_company_name", table_name="departments")
    op.drop_index("ix_departments_company_id", table_name="departments")
    op.drop_table("departments")
    op.drop_index("ix_companies_name", table_name="companies")
    op.drop_table("companies")
    op.drop_index("ix_roles_code", table_name="roles")
    op.drop_table("roles")
