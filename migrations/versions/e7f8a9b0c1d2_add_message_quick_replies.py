"""add message quick_replies

Cột mới cho phép AI (khi tư vấn khách qua SYSTEM_INSTRUCTION_PUBLIC) đính kèm 2-4 lựa chọn
trả lời ngắn cho câu hỏi khảo sát nhu cầu vừa đặt ra (vd. "Để ở"/"Đầu tư"), để khách bấm
chọn thay vì phải gõ. Model tự quyết định có option hay không theo từng câu hỏi — không có
bộ option cố định nào ở tầng backend. Xem backend/ai/prompts.py::ConsultAnswer và
backend/services/agent_pipeline.py.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: str | Sequence[str] | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("quick_replies", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("quick_replies")
