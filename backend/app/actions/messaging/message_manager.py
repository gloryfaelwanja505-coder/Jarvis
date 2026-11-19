from sqlalchemy.orm import Session

from app.actions.drafts import save_draft
from app.schemas.assistant import ActionDraftCreate


class MessageManager:
    def create_draft(
        self,
        db: Session,
        recipient: str,
        body: str,
    ):
        return save_draft(
            db,
            ActionDraftCreate(action_type="message", recipient=recipient, body=body),
        )

    def send(self, recipient: str, body: str) -> None:
        if not recipient.strip() or not body.strip():
            raise ValueError("A recipient and message body are required.")
        raise RuntimeError("No authorized messaging delivery adapter is configured.")
