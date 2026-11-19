"""Prevent overlapping active calling sessions."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_single_active_call"
down_revision: Union[str, None] = "0001_calling_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_call_sessions_single_active",
        "call_sessions",
        [sa.text("(1)")],
        unique=True,
        sqlite_where=sa.text(
            "status IN ('queued', 'ringing', 'accepted', 'connecting', 'active')"
        ),
        postgresql_where=sa.text(
            "status IN ('queued', 'ringing', 'accepted', 'connecting', 'active')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_call_sessions_single_active", table_name="call_sessions")
