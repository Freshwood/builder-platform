"""Agent run provenance: prompt fingerprint, model role, routing reason, duration (ADR-0006).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("prompt_fingerprint", sa.String(32)))
    op.add_column("agent_runs", sa.Column("safety_rules_version", sa.String(16)))
    op.add_column("agent_runs", sa.Column("model_role", sa.String(16)))
    op.add_column("agent_runs", sa.Column("routing_reason", sa.String(32)))
    op.add_column("agent_runs", sa.Column("duration_ms", sa.Integer()))


def downgrade() -> None:
    for column in (
        "duration_ms",
        "routing_reason",
        "model_role",
        "safety_rules_version",
        "prompt_fingerprint",
    ):
        op.drop_column("agent_runs", column)
