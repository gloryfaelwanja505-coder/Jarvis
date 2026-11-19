"""Persist assistant task execution and recovery checkpoints."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_assistant_task_recovery"
down_revision: Union[str, None] = "0002_single_active_call"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assistant_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(length=36),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_message_id",
            sa.String(length=36),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assistant_message_id",
            sa.String(length=36),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_message_id", name="uq_assistant_tasks_user_message_id"),
    )
    op.create_index("ix_assistant_tasks_conversation_id", "assistant_tasks", ["conversation_id"])
    op.create_index(
        "ix_assistant_tasks_conversation_created",
        "assistant_tasks",
        ["conversation_id", "created_at"],
    )
    op.create_table(
        "assistant_task_checkpoints",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(length=36),
            sa.ForeignKey("assistant_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("checkpoint_number", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("detail", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "task_id",
            "checkpoint_number",
            name="uq_assistant_task_checkpoint_number",
        ),
    )
    op.create_index(
        "ix_assistant_task_checkpoints_task_id",
        "assistant_task_checkpoints",
        ["task_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_task_checkpoints_task_id", table_name="assistant_task_checkpoints")
    op.drop_table("assistant_task_checkpoints")
    op.drop_index("ix_assistant_tasks_conversation_created", table_name="assistant_tasks")
    op.drop_index("ix_assistant_tasks_conversation_id", table_name="assistant_tasks")
    op.drop_table("assistant_tasks")
