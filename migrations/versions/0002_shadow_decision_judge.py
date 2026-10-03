"""Add nullable shadow decision judge result.

Revision ID: 0002_shadow_decision_judge
Revises: 0001_platform_poc
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_shadow_decision_judge"
down_revision: str | Sequence[str] | None = "0001_platform_poc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_results",
        sa.Column("decision_judge_result", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluation_results", "decision_judge_result")
