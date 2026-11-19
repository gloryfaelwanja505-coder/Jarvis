from sqlalchemy.orm import Session

from app.models import AssistantAction, AssistantActionAudit
from app.schemas.assistant import ActionDraftCreate


def save_draft(db: Session, payload: ActionDraftCreate) -> AssistantAction:
    action = AssistantAction(
        action_type=payload.action_type,
        recipient=payload.recipient.strip(),
        subject=payload.subject.strip() if payload.subject else None,
        body=payload.body.strip(),
        status="draft",
    )
    db.add(action)
    db.flush()
    db.add(
        AssistantActionAudit(
            action_id=action.id,
            event="draft_created",
            detail="Draft saved locally; no message was sent.",
        )
    )
    db.commit()
    db.refresh(action)
    return action
