"""Persist assistant profile, approved memory, and action audit records."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_assistant_memory_actions"
down_revision: Union[str, None] = "0003_assistant_task_recovery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assistant_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("selected_model", sa.String(length=160), nullable=False),
        sa.Column("personality", sa.String(length=500), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "assistant_memories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(length=80), nullable=False, unique=True),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "assistant_actions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("action_type", sa.String(length=24), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "assistant_action_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("action_id", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=40), nullable=False),
        sa.Column("detail", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_assistant_action_audit_action_id",
        "assistant_action_audit",
        ["action_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_action_audit_action_id", table_name="assistant_action_audit")
    op.drop_table("assistant_action_audit")
    op.drop_table("assistant_actions")
    op.drop_table("assistant_memories")
    op.drop_table("assistant_profiles")
