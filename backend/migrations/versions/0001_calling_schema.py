"""Add persistent calling schedules, sessions, and attempts."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_calling_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calling_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("do_not_disturb", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Africa/Nairobi"),
        sa.Column("retry_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("retry_delay_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("telephone_fallback_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("telephone_billing_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("transcript_retention_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "call_schedules",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("local_time", sa.Time(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("prompt_context", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "call_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("occurrence_key", sa.String(length=96), nullable=True),
        sa.Column("schedule_id", sa.String(length=32), sa.ForeignKey("call_schedules.id"), nullable=True),
        sa.Column("occurrence_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("channel", sa.String(length=24), nullable=True),
        sa.Column("external_call_id", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("outcome", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("occurrence_key", name="uq_call_sessions_occurrence_key"),
    )
    op.create_table(
        "call_attempts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("call_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("result", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", "attempt_number", name="uq_call_attempts_number"),
    )
    op.create_index("ix_call_attempts_session_id", "call_attempts", ["session_id"])

def downgrade() -> None:
    op.drop_index("ix_call_attempts_session_id", table_name="call_attempts")
    op.drop_table("call_attempts")
    op.drop_table("call_sessions")
    op.drop_table("call_schedules")
    op.drop_table("calling_preferences")
