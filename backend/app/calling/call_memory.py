import re

from sqlalchemy.orm import Session

from app.models import CallSession


MAX_TRANSCRIPT_CHARACTERS = 60_000
SENSITIVE_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(?:password|passcode|secret|api[\s_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gsk_[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{20,})\b"),
)


def append_transcript(
    db: Session,
    session: CallSession,
    speaker: str,
    text: str,
) -> None:
    if speaker not in {"owner", "assistant"}:
        raise ValueError("Transcript speaker must be owner or assistant.")
    from app.models import CallingPreferences

    preferences = db.get(CallingPreferences, 1)
    if preferences is None or not preferences.transcript_retention_enabled:
        return
    content = text.strip()
    if not content:
        return
    for pattern in SENSITIVE_PATTERNS:
        content = pattern.sub("[REDACTED]", content)
    entry = f"{speaker}: {content}"
    combined = f"{session.transcript}\n{entry}".strip()
    if len(combined) > MAX_TRANSCRIPT_CHARACTERS:
        raise ValueError("Call transcript has reached its storage limit.")
    session.transcript = combined
    db.add(session)
    db.commit()
