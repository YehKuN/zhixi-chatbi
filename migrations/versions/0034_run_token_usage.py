"""Persist per-Run token usage for platform administration."""

import sqlalchemy as sa
from alembic import op

revision = "0034_run_token_usage"
down_revision = "0033_enterprise_data_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("usage_input_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("usage_output_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("usage_total_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("usage_model_calls", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("usage_model_calls")
        batch.drop_column("usage_total_tokens")
        batch.drop_column("usage_output_tokens")
        batch.drop_column("usage_input_tokens")
