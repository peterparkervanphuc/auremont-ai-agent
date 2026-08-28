"""add durable incremental customer conversation summaries

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-08-25

Renumbered when feature/Giang merged into develop: this migration was authored as
b1c2d3e4f5a6 off a1b2c3d4e5f7, but the lead-capture migration had meanwhile taken that
same id on develop from the same parent. Two files sharing one revision id leave alembic
unable to resolve `head` at all, so this one moves to a free id and chains after the
lead migration instead of racing it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | Sequence[str] | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_conversation_summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("last_processed_message_id", sa.Integer(), nullable=False),
        sa.Column("source_message_count", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_id"),
    )
    op.create_index(
        "ix_customer_conversation_summaries_id",
        "customer_conversation_summaries",
        ["id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_conversation_summaries_id",
        table_name="customer_conversation_summaries",
    )
    op.drop_table("customer_conversation_summaries")
