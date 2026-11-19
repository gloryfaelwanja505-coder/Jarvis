import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.calling.call_routing import CallRouter
from app.calling.call_sessions import CallConnectionHub
from app.config import Settings
from app.models import CallAttempt, CallSession
from app.models.conversation import utc_now

logger = logging.getLogger(__name__)


class CallManager:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        hub: CallConnectionHub,
        router: CallRouter,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.hub = hub
        self.router = router

    async def run_scheduled(self, schedule_id: str, scheduled_at: datetime | None = None) -> None:
        scheduled_at = scheduled_at or datetime.now(timezone.utc)
        await self.router.run_schedule(schedule_id, scheduled_at)

    def recover_interrupted_sessions(self) -> None:
        with self.session_factory() as db:
            sessions = db.scalars(
                select(CallSession).where(
                    CallSession.status.in_(
                        ("queued", "ringing", "accepted", "connecting", "active")
                    )
                ).options(selectinload(CallSession.attempts))
            ).all()
            ended_at = utc_now()
            for session in sessions:
                session.status = "failed"
                session.outcome = "backend_restarted"
                session.ended_at = ended_at
                for attempt in session.attempts:
                    if attempt.status == "in_progress":
                        attempt.status = "failed"
                        attempt.result = "backend_restarted"
                        attempt.completed_at = ended_at
                if session.started_at:
                    started_at = session.started_at
                    if started_at.tzinfo is None:
                        started_at = started_at.replace(tzinfo=timezone.utc)
                    session.duration_seconds = max(
                        0,
                        int((ended_at - started_at).total_seconds()),
                    )
            db.commit()

    async def control_call(self, message: dict[str, object]) -> dict[str, object]:
        call_id = message.get("call_id")
        message_type = message.get("type")
        if not isinstance(call_id, str) or not isinstance(message_type, str):
            raise ValueError("Call control message is incomplete.")
        with self.session_factory() as db:
            session = db.scalar(select(CallSession).where(CallSession.id == call_id))
            if session is None:
                raise ValueError("Call session not found.")
            if (
                message_type == "answer"
                and session.status in {"connecting", "active"}
                and session.channel == "webrtc"
            ):
                return {"type": "call_status", "call_id": call_id, "status": session.status}
            if (
                message_type == "decline"
                and session.status == "declined"
                and session.outcome == "owner_declined"
            ):
                return {"type": "call_status", "call_id": call_id, "status": session.status}
            if (
                message_type == "end"
                and session.status in {"completed", "cancelled"}
                and session.outcome == "owner_ended_call"
            ):
                return {"type": "call_status", "call_id": call_id, "status": session.status}
            if message_type in {"answer", "decline", "end"}:
                if session.status not in {"queued", "ringing", "accepted", "connecting", "active"}:
                    raise ValueError("Call session is no longer active.")
                await self.hub.signal(message)
                if message_type == "answer":
                    session.status = "connecting"
                    session.channel = "webrtc"
                    session.outcome = "owner_accepted_waiting_for_webrtc"
                elif message_type == "decline":
                    session.status = "declined"
                    session.outcome = "owner_declined"
                    session.ended_at = utc_now()
                else:
                    session.status = "completed" if session.started_at else "cancelled"
                    session.outcome = "owner_ended_call"
                    session.ended_at = utc_now()
                    if session.started_at:
                        started_at = session.started_at
                        if started_at.tzinfo is None:
                            started_at = started_at.replace(tzinfo=timezone.utc)
                        session.duration_seconds = max(
                            0,
                            int((session.ended_at - started_at).total_seconds()),
                        )
                db.commit()
                if message_type in {"end", "decline"}:
                    await self.router.webrtc.close(call_id)
                if message_type == "end":
                    await self.summarize_session(call_id)
                return {"type": "call_status", "call_id": call_id, "status": session.status}

            payload = message.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("Signaling payload must be an object.")
            if message_type == "offer":
                if session.status not in {"connecting", "ringing"}:
                    raise ValueError("A WebRTC offer is not expected in this call state.")
                session.status = "connecting"
                db.commit()
                sdp = payload.get("sdp")
                if not isinstance(sdp, str) or len(sdp) > 250_000:
                    raise ValueError("Invalid SDP offer.")
                try:
                    answer = await self.router.webrtc.accept_offer(
                        call_id,
                        sdp,
                        session.schedule.prompt_context if session.schedule else "morning",
                    )
                except Exception as exc:
                    logger.exception("Could not negotiate WebRTC offer for call %s", call_id)
                    session.status = "failed"
                    session.outcome = "webrtc_offer_negotiation_failed"
                    session.ended_at = utc_now()
                    db.commit()
                    await self.router.webrtc.close(call_id)
                    await self.hub.publish(
                        {"type": "call_status", "call_id": call_id, "status": "failed"}
                    )
                    raise ValueError("WebRTC offer negotiation failed.") from exc
                return {
                    "type": "answer_sdp",
                    "call_id": call_id,
                    "payload": {"sdp": answer},
                }
            if message_type == "ice_candidate":
                await self.router.webrtc.add_ice_candidate(call_id, payload)
                return {"type": "signal_ack", "call_id": call_id}
            if message_type == "answer_sdp":
                raise ValueError("Clients may not send a server WebRTC answer.")
        raise ValueError("Unsupported call control message.")

    async def mark_connected(self, call_id: str) -> None:
        with self.session_factory() as db:
            session = db.get(CallSession, call_id)
            if session is None or session.status not in {"connecting", "accepted"}:
                return
            session.status = "active"
            session.started_at = utc_now()
            session.outcome = "webrtc_media_connected"
            db.commit()
        await self.hub.publish({"type": "call_status", "call_id": call_id, "status": "active"})

    async def mark_disconnected(self, call_id: str) -> None:
        with self.session_factory() as db:
            session = db.get(CallSession, call_id)
            if session is None or session.status not in {"connecting", "active"}:
                return
            session.status = "failed" if session.started_at else "missed"
            session.ended_at = utc_now()
            session.outcome = "webrtc_connection_lost"
            if session.started_at:
                started_at = session.started_at
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                session.duration_seconds = max(
                    0,
                    int((session.ended_at - started_at).total_seconds()),
                )
            status = session.status
            db.commit()
        await self.hub.publish(
            {"type": "call_status", "call_id": call_id, "status": status}
        )

    async def summarize_session(self, call_id: str) -> None:
        with self.session_factory() as db:
            session = db.get(CallSession, call_id)
            transcript = session.transcript if session is not None else ""
        if transcript:
            await self._summarize(call_id, transcript)

    async def _summarize(self, call_id: str, transcript: str) -> None:
        try:
            summary = await self.router.conversation_engine.summarize(transcript)
        except Exception:
            logger.exception("Could not summarize call %s", call_id)
            return
        with self.session_factory() as db:
            session = db.get(CallSession, call_id)
            if session is not None:
                session.summary = summary[:4_000]
                db.commit()
