"""add leads table and user contact columns

A lead is a PERSON, not a conversation, so the tier cannot live on `chat_sessions`: the
`channel` column added in a1b2c3d4e5f7 splits one customer's AI thread and live-Sale
thread into two rows, and `sale_live` reads LIVE rows only — a tier written on the AI row
would be invisible on exactly the row a Sale looks at. Identity is `customer_id` once
registered and `visitor_token` while anonymous, both UNIQUE-nullable (MySQL and SQLite
both allow many NULLs under UNIQUE), mirroring how `chat_sessions` already models the
same person in the same two states.

`users` gains `full_name` and `phone`, captured by the customer registration gate. Note
`full_name` has been declared on CustomerRegisterRequest since that gate shipped but was
never persisted; this is the column that finally gives it somewhere to go.

Nothing is backfilled, deliberately. Every pre-existing account gets NULL contact details
because they were never asked, and no pre-existing person becomes a lead until their next
message: a score is derived from signals in what someone said, and no such signal was ever
recorded before now. Inventing tiers from historical rows would fill the Sale's queue with
verdicts that no evidence supports.

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f7
Create Date: 2026-08-25
"""

import sqlalchemy as sa
from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("visitor_token", sa.String(length=64), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("tier", sa.String(length=10), nullable=False, server_default="cold"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rule_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("soft_score", sa.Integer(), nullable=True),
        sa.Column("urgency", sa.String(length=12), nullable=True),
        sa.Column("purpose", sa.String(length=20), nullable=True),
        sa.Column("signals", sa.JSON(), nullable=True),
        sa.Column("detection_method", sa.String(length=20), nullable=False, server_default="rule"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("analysis_version", sa.String(length=20), nullable=True),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_scored_turn", sa.Integer(), nullable=True),
        sa.Column("scored_at", sa.DateTime(), nullable=True),
        sa.Column("llm_scored_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_leads_id", "leads", ["id"])
    op.create_index("ix_leads_customer_id", "leads", ["customer_id"], unique=True)
    op.create_index("ix_leads_visitor_token", "leads", ["visitor_token"], unique=True)
    op.create_index("ix_leads_project_id", "leads", ["project_id"])
    op.create_index("ix_leads_tier", "leads", ["tier"])
    op.create_index("ix_leads_scored_at", "leads", ["scored_at"])

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("full_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("phone", sa.String(length=20), nullable=True))
        batch_op.create_index(batch_op.f("ix_users_phone"), ["phone"])


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_phone"))
        batch_op.drop_column("phone")
        batch_op.drop_column("full_name")

    op.drop_index("ix_leads_scored_at", table_name="leads")
    op.drop_index("ix_leads_tier", table_name="leads")
    op.drop_index("ix_leads_project_id", table_name="leads")
    op.drop_index("ix_leads_visitor_token", table_name="leads")
    op.drop_index("ix_leads_customer_id", table_name="leads")
    op.drop_index("ix_leads_id", table_name="leads")
    op.drop_table("leads")
