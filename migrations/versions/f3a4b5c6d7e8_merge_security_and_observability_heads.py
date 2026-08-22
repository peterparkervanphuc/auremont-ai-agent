"""merge document security findings and observability heads

Revision ID: f3a4b5c6d7e8
Revises: b2c3d4e5f6a7, e5f6a7b8c9d0
Create Date: 2026-08-23

"""

from collections.abc import Sequence


revision: str = "f3a4b5c6d7e8"
down_revision: str | Sequence[str] | None = (
    "b2c3d4e5f6a7",
    "e5f6a7b8c9d0",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join independent migration branches; schema changes are in the parents."""


def downgrade() -> None:
    """Split back to the parent revisions without changing schema."""
