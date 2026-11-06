"""Scope business data to enterprises and backfill legacy rows."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_enterprise_data_scope"
down_revision = "0032_enterprise_auth"
branch_labels = None
depends_on = None


def _first_enterprise_id() -> str | None:
    bind = op.get_bind()
    row = bind.execute(
        sa.text("SELECT id FROM enterprises ORDER BY created_at ASC, id ASC LIMIT 1")
    ).first()
    return None if row is None else str(row[0])


def upgrade() -> None:
    op.add_column("sessions", sa.Column("enterprise_id", sa.String(length=120), nullable=True))
    op.create_index("ix_sessions_enterprise_id", "sessions", ["enterprise_id"])
    op.add_column("data_sources", sa.Column("enterprise_id", sa.String(length=120), nullable=True))
    op.create_index("ix_data_sources_enterprise_id", "data_sources", ["enterprise_id"])
    op.add_column(
        "model_profiles", sa.Column("enterprise_id", sa.String(length=120), nullable=True)
    )
    op.create_index("ix_model_profiles_enterprise_id", "model_profiles", ["enterprise_id"])

    # 旧数据归到底一个企业（生产库即测试账号所属企业），实现“现有业务数据转到测试账号”。
    enterprise_id = _first_enterprise_id()
    if enterprise_id is not None:
        for table in ("sessions", "data_sources", "model_profiles"):
            op.execute(
                sa.text(
                    f"UPDATE {table} SET enterprise_id = :enterprise_id "
                    "WHERE enterprise_id IS NULL"
                ).bindparams(enterprise_id=enterprise_id)
            )

    op.drop_index("uq_model_profiles_single_active", table_name="model_profiles")
    op.create_index(
        "uq_model_profiles_enterprise_active",
        "model_profiles",
        ["enterprise_id", "is_active"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_model_profiles_enterprise_active", table_name="model_profiles")
    op.create_index(
        "uq_model_profiles_single_active",
        "model_profiles",
        ["is_active"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
    )
    op.drop_index("ix_model_profiles_enterprise_id", table_name="model_profiles")
    op.drop_column("model_profiles", "enterprise_id")
    op.drop_index("ix_data_sources_enterprise_id", table_name="data_sources")
    op.drop_column("data_sources", "enterprise_id")
    op.drop_index("ix_sessions_enterprise_id", table_name="sessions")
    op.drop_column("sessions", "enterprise_id")
