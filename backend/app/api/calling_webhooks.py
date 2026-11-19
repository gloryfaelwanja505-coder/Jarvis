from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException, Request, WebSocket
from sqlalchemy import select

from app.calling.providers.telephone import twilio_status_is_final
from app.models import CallSession
from app.models.conversation import utc_now

router = APIRouter()


async def _verified_form(request: Request) -> dict[str, str]:
    raw = (await request.body()).decode("utf-8", errors="replace")
    values = dict(parse_qsl(raw, keep_blank_values=True, max_num_fields=100))
    telephone = request.app.state.calling_telephone
    if not telephone.verify_webhook(
        str(request.url),
        values,
        request.headers.get("X-Twilio-Signature"),
    ):
        raise HTTPException(status_code=403, detail="Invalid telephony webhook signature.")
    return values


@router.post("/twilio/status")
async def twilio_status(request: Request, call_id: str) -> dict[str, str]:
    values = await _verified_form(request)
    provider_status = values.get("CallStatus", "")
    external_id = values.get("CallSid", "")
    if not external_id:
        raise HTTPException(status_code=422, detail="Missing provider call identifier.")
    session_factory = request.app.state.session_factory
    with session_factory() as db:
        session = db.scalar(select(CallSession).where(CallSession.id == call_id))
        if session is None or (
            session.external_call_id is not None
            and session.external_call_id != external_id
        ) or (
            session.external_call_id is None and session.status != "unknown"
        ):
            raise HTTPException(status_code=404, detail="Telephony call session not found.")
        if session.external_call_id is None:
            session.external_call_id = external_id
        if session.status in {
            "completed",
            "missed",
            "failed",
            "declined",
            "cancelled",
            "skipped",
        }:
            return {"received": "true"}
        if provider_status == "in-progress":
            session.status = "active"
            session.started_at = session.started_at or utc_now()
        elif twilio_status_is_final(provider_status):
            session.ended_at = utc_now()
            if provider_status == "completed":
                session.status = "completed"
                try:
                    session.duration_seconds = min(
                        86_400,
                        max(0, int(values.get("CallDuration", "0"))),
                    )
                except ValueError:
                    session.duration_seconds = None
                session.outcome = "telephone_call_completed"
            else:
                session.status = "missed"
                session.outcome = f"telephone_{provider_status}"
        db.commit()
        should_summarize = session.status == "completed" and bool(session.transcript)
    if should_summarize:
        await request.app.state.calling_manager.summarize_session(call_id)
    return {"received": "true"}


@router.websocket("/twilio/media")
async def twilio_media(websocket: WebSocket, call_id: str) -> None:
    telephone = websocket.app.state.calling_telephone
    if not telephone.configured or websocket.app.state.settings.test_mode:
        await websocket.close(code=1013, reason="Live telephony is disabled.")
        return
    if not telephone.voice_stream_available:
        await websocket.close(code=1013, reason="Local speech services are unavailable.")
        return
    signature = websocket.headers.get("X-Twilio-Signature")
    if not telephone.verify_webhook(str(websocket.url), {}, signature):
        await websocket.close(code=4403, reason="Invalid telephony stream signature.")
        return
    await telephone.stream_conversation(
        websocket,
        call_id,
        websocket.app.state.session_factory,
    )
