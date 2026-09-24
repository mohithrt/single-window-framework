"""Add application assistant history and mock integration transaction logs."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260924_08"
down_revision: str | None = "20260924_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_chat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False, server_default="Application assistant"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_chat_sessions_user_application", "ai_chat_sessions", ["user_id", "application_id", "updated_at"])
    op.create_table(
        "ai_chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("ai_chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured_data", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('USER', 'ASSISTANT')", name="ck_ai_chat_messages_role"),
    )
    op.create_index("ix_ai_chat_messages_session_created", "ai_chat_messages", ["session_id", "created_at"])
    op.create_table(
        "integration_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_code", sa.String(length=32), nullable=False),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id", ondelete="SET NULL")),
        sa.Column("submitted_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False, unique=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_integration_transactions_provider_created", "integration_transactions", ["provider_code", "created_at"])
    op.create_index("ix_integration_transactions_application", "integration_transactions", ["application_id"])


def downgrade() -> None:
    op.drop_index("ix_integration_transactions_application", table_name="integration_transactions")
    op.drop_index("ix_integration_transactions_provider_created", table_name="integration_transactions")
    op.drop_table("integration_transactions")
    op.drop_index("ix_ai_chat_messages_session_created", table_name="ai_chat_messages")
    op.drop_table("ai_chat_messages")
    op.drop_index("ix_ai_chat_sessions_user_application", table_name="ai_chat_sessions")
    op.drop_table("ai_chat_sessions")
