from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AssistantMemory


class ContextManager:
    def approved_preferences(self, db: Session) -> list[tuple[str, str]]:
        rows = db.scalars(
            select(AssistantMemory)
            .where(AssistantMemory.approved.is_(True))
            .order_by(AssistantMemory.created_at)
            .limit(50)
        ).all()
        return [(row.key, row.value) for row in rows]
