"""Add enterprise and user authentication tables."""

import sqlalchemy as sa
from alembic import op

revision = "0032_enterprise_auth"
down_revision = "0031_model_profile_reasoning_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enterprises",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("company_size", sa.String(length=50), nullable=True),
        sa.Column("contact_name", sa.String(length=80), nullable=False),
        sa.Column("contact_phone", sa.String(length=40), nullable=False),
        sa.Column("contact_email", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_enterprises_code"),
        sa.UniqueConstraint("name", name="uq_enterprises_name"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("enterprise_id", sa.String(length=120), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('enterprise_admin', 'employee')", name="ck_users_role"
        ),
        sa.ForeignKeyConstraint(
            ["enterprise_id"], ["enterprises.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_enterprise_id", "users", ["enterprise_id"])
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=120), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_users_enterprise_id", table_name="users")
    op.drop_table("users")
    op.drop_table("enterprises")
