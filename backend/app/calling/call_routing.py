import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.calling.call_sessions import CallConnectionHub
from app.calling.conversation_engine import ConversationEngine
from app.calling.retry_manager import planned_attempts
from app.config import Settings
from app.models import CallAttempt, CallSchedule, CallSession, CallingPreferences
from app.models.conversation import utc_now
from app.calling.providers.telephone import (
    TelephoneCallUncertain,
    TelephoneUnavailable,
    TwilioTelephoneProvider,
)
from app.calling.providers.webrtc import WebRTCVoiceProvider

logger = logging.getLogger(__name__)


class CallRouter:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        hub: CallConnectionHub,
        webrtc: WebRTCVoiceProvider,
        telephone: TwilioTelephoneProvider,
        conversation_engine: ConversationEngine,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.hub = hub
        self.webrtc = webrtc
        self.telephone = telephone
        self.conversation_engine = conversation_engine

    async def run_schedule(self, schedule_id: str, scheduled_at: datetime) -> CallSession | None:
        with self.session_factory() as db:
            schedule = db.get(CallSchedule, schedule_id)
            preferences = db.get(CallingPreferences, 1)
            if schedule is None or preferences is None:
                return None
            local_date = scheduled_at.astimezone(ZoneInfo(preferences.timezone)).date()
            occurrence_key = f"{schedule.id}:{local_date.isoformat()}"
            existing = db.scalar(
                select(CallSession).where(CallSession.occurrence_key == occurrence_key)
            )
            if existing is not None:
                return existing
            active = db.scalar(
                select(CallSession)
                .where(CallSession.status.in_(("queued", "ringing", "accepted", "connecting", "active")))
                .order_by(CallSession.created_at.desc())
                .limit(1)
            )
            session = CallSession(
                id=str(uuid4()),
                occurrence_key=occurrence_key,
                schedule_id=schedule.id,
                occurrence_date=local_date,
                status="skipped" if active is not None else "queued",
                created_at=utc_now(),
                outcome=f"another_call_active:{active.id}" if active is not None else None,
            )
            db.add(session)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                existing = db.scalar(
                    select(CallSession).where(CallSession.occurrence_key == occurrence_key)
                )
                if existing is not None:
                    return existing
                active = db.scalar(
                    select(CallSession)
                    .where(
                        CallSession.status.in_(
                            ("queued", "ringing", "accepted", "connecting", "active")
                        )
                    )
                    .order_by(CallSession.created_at.desc())
                    .limit(1)
                )
                if active is None:
                    raise
                session = CallSession(
                    id=str(uuid4()),
                    occurrence_key=occurrence_key,
                    schedule_id=schedule.id,
                    occurrence_date=local_date,
                    status="skipped",
                    created_at=utc_now(),
                    outcome=f"another_call_active:{active.id}",
                )
                db.add(session)
                db.commit()
                return session
            db.refresh(session)
            call_id = session.id
            context = schedule.prompt_context

        if active is not None:
            return session

        with self.session_factory() as db:
            preferences = db.get(CallingPreferences, 1)
            session = db.get(CallSession, call_id)
            if preferences is None or session is None:
                return None
            if not preferences.enabled:
                session.status = "skipped"
                session.outcome = "scheduled_calling_disabled"
                db.commit()
                return session
            if preferences.do_not_disturb:
                session.status = "skipped"
                session.outcome = "do_not_disturb"
                db.commit()
                return session

            channels = ["webrtc"]
            telephone_allowed = (
                preferences.telephone_fallback_enabled
                and preferences.telephone_billing_confirmed
                and self.telephone.configured
                and self.telephone.voice_stream_available
                and await self.conversation_engine.is_available()
                and not self.settings.test_mode
            )
            if telephone_allowed:
                channels.append("telephone")
            attempts = planned_attempts(preferences.retry_limit, channels)

        for attempt_index, (attempt_number, channel) in enumerate(attempts):
            with self.session_factory() as db:
                session = db.get(CallSession, call_id)
                if session is None or session.status in {"active", "completed"}:
                    return session
                attempt = CallAttempt(
                    session_id=call_id,
                    attempt_number=attempt_number,
                    channel=channel,
                    status="in_progress",
                    created_at=utc_now(),
                )
                db.add(attempt)
                db.commit()
                attempt_id = attempt.id

            try:
                result = await self._attempt(call_id, context, channel)
            except Exception:
                logger.exception("Call attempt failed for session %s on %s", call_id, channel)
                result = AttemptResult("failed", f"{channel}_attempt_error")
            with self.session_factory() as db:
                attempt = db.get(CallAttempt, attempt_id)
                session = db.get(CallSession, call_id)
                if attempt is None or session is None:
                    return None
                attempt.status = result.status
                attempt.result = result.detail[:160]
                attempt.completed_at = utc_now()
                if result.status == "uncertain":
                    session.status = "unknown"
                    session.channel = channel
                    session.ended_at = utc_now()
                    session.outcome = (
                        "Telephone provider did not confirm the call; no retry was attempted "
                        "to avoid a duplicate charge."
                    )
                    db.commit()
                    return session
                if result.status in {"accepted", "ringing"}:
                    if session.status not in {"connecting", "active", "completed"}:
                        session.status = result.status
                    session.channel = channel
                    session.outcome = result.detail[:160]
                    db.commit()
                    return session
                if result.status == "declined":
                    session.status = "declined"
                    session.ended_at = utc_now()
                    session.outcome = result.detail[:160]
                    db.commit()
                    return session
                db.commit()
            if attempt_index + 1 < len(attempts) and (attempt_index + 1) % len(channels) == 0:
                await asyncio.sleep(preferences.retry_delay_seconds)

        with self.session_factory() as db:
            session = db.get(CallSession, call_id)
            if session is not None:
                session.status = "missed"
                session.ended_at = utc_now()
                session.outcome = "all_calling_channels_failed"
                db.commit()
                db.refresh(session)
            return session

    async def _attempt(self, call_id: str, context: str, channel: str) -> "AttemptResult":
        if channel == "webrtc":
            if not self.webrtc.media_available:
                return AttemptResult("failed", "local_webrtc_voice_stack_unavailable")
            if not await self.conversation_engine.is_available():
                return AttemptResult("failed", "configured_ai_provider_unavailable")
            if not self.hub.connected_clients:
                return AttemptResult("failed", "no_authenticated_calling_client_connected")
            queue = self.hub.create_call_queue(call_id)
            await self.hub.publish(
                {
                    "type": "incoming_call",
                    "call_id": call_id,
                    "context": context,
                    "channel": "webrtc",
                }
            )
            try:
                action = await asyncio.wait_for(
                    queue.get(),
                    timeout=self.settings.call_ring_timeout_seconds,
                )
            except TimeoutError:
                return AttemptResult("missed", "internet_call_not_answered")
            finally:
                self.hub.discard_call_queue(call_id)
            if action.get("type") == "decline":
                return AttemptResult("declined", "owner_declined_incoming_call")
            if action.get("type") == "answer":
                return AttemptResult("accepted", "owner_accepted_webrtc_invitation")
            return AttemptResult("missed", "call_ended_before_answer")

        if channel == "telephone":
            if not self.telephone.voice_stream_available:
                return AttemptResult("failed", "telephone_voice_stream_not_available")
            with self.session_factory() as db:
                session = db.get(CallSession, call_id)
                if session is None:
                    return AttemptResult("failed", "call_session_not_found")
                try:
                    external_id = await self.telephone.place_call(session)
                except TelephoneCallUncertain as exc:
                    return AttemptResult("uncertain", str(exc))
                except TelephoneUnavailable as exc:
                    return AttemptResult("failed", str(exc))
                session.channel = "telephone"
                session.external_call_id = external_id
                db.commit()
            return AttemptResult("ringing", "telephone_provider_accepted_call")

        return AttemptResult("failed", "unsupported_call_channel")


class AttemptResult:
    def __init__(self, status: str, detail: str) -> None:
        self.status = status
        self.detail = detail
