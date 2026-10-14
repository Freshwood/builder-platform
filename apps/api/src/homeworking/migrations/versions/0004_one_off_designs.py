"""Every project is a one-off design (ADR-0008): no construction packs, no templates.

Projects whose log ever used a construction pack (the raised bed) cannot be replayed without the
pack, so they are removed. Their agent runs stay for cost and provenance; only the link to the
project is cleared. Design projects keep their JSON documents, the repository upcasts them from
schema 1 to 2 when they are read.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-14
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DESIGN = "design"


def _uses_pack(command: Any) -> bool:
    if not isinstance(command, dict):
        return False
    if command.get("pack_id", _DESIGN) != _DESIGN:
        return True
    inputs = command.get("inputs")
    return isinstance(inputs, dict) and inputs.get("pack_id", _DESIGN) != _DESIGN


def upgrade() -> None:
    bind = op.get_bind()
    projects = sa.table("projects", sa.column("id"), sa.column("pack_id"))
    commands = sa.table(
        "project_commands", sa.column("project_id"), sa.column("command", sa.JSON())
    )
    runs = sa.table("agent_runs", sa.column("project_id"))

    doomed = {
        row.id
        for row in bind.execute(sa.select(projects.c.id, projects.c.pack_id))
        if row.pack_id != _DESIGN
    }
    for row in bind.execute(sa.select(commands.c.project_id, commands.c.command)):
        if _uses_pack(row.command):
            doomed.add(row.project_id)
    if doomed:
        ids = list(doomed)
        bind.execute(sa.update(runs).where(runs.c.project_id.in_(ids)).values(project_id=None))
        bind.execute(sa.delete(commands).where(commands.c.project_id.in_(ids)))
        bind.execute(sa.delete(projects).where(projects.c.id.in_(ids)))

    with op.batch_alter_table("projects") as batch:
        batch.drop_column("pack_id")
    with op.batch_alter_table("project_commands") as batch:
        batch.alter_column(
            "pack_version", new_column_name="design_version", existing_type=sa.String(32)
        )


def downgrade() -> None:
    with op.batch_alter_table("project_commands") as batch:
        batch.alter_column(
            "design_version", new_column_name="pack_version", existing_type=sa.String(32)
        )
    with op.batch_alter_table("projects") as batch:
        batch.add_column(
            sa.Column("pack_id", sa.String(64), nullable=False, server_default=_DESIGN)
        )
