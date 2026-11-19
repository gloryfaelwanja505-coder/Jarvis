from sqlalchemy.orm import Session

from app.actions.drafts import save_draft
from app.schemas.assistant import ActionDraftCreate


class EmailDrafts:
    def create(
        self,
        db: Session,
        recipient: str,
        subject: str,
        body: str,
    ):
        return save_draft(
            db,
            ActionDraftCreate(
                action_type="email",
                recipient=recipient,
                subject=subject,
                body=body,
            ),
        )
