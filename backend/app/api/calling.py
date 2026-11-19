import logging
from datetime import datetime
from importlib.util import find_spec
import shutil
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import get_db
from app.calling.providers.webrtc import webrtc_dependencies_installed
from app.calling.scheduler import CallScheduler
from app.calling.schemas import (
    CallControlMessage,
    IceServerResponse,
    CallSessionResponse,
    CallingStatusResponse,
    PreferencesResponse,
    PreferencesUpdate,
    ScheduleResponse,
    ScheduleUpdate,
)
from app.calling.security import require_calling_access, websocket_token_matches
from app.calling.call_sessions import decode_signal
from app.config import Settings
from app.models import CallSchedule, CallSession, CallingPreferences
from app.models.conversation import utc_now

router = APIRouter()
Access = Annotated[str, Depends(require_calling_access)]
logger = logging.getLogger(__name__)


@router.get("/status", response_model=CallingStatusResponse)
async def calling_status(request: Request, db: Session = Depends(get_db)) -> CallingStatusResponse:
    settings: Settings = request.app.state.settings
    preferences = db.get(CallingPreferences, 1)
    if preferences is None:
        raise HTTPException(status_code=503, detail="Calling database has not initialized.")
    engine = request.app.state.calling_conversation_engine
    speech_to_text = find_spec("faster_whisper") is not None and find_spec("numpy") is not None
    ai_available = await engine.is_available()
    return CallingStatusResponse(
        authentication_configured=settings.calling_auth_configured,
        scheduler_running=request.app.state.calling_scheduler.running,
        ai_provider=settings.ai_provider,
        ai_available=ai_available,
        webrtc_signaling_available=settings.calling_auth_configured,
        webrtc_media_available=request.app.state.calling_webrtc.media_available and ai_available,
        speech_to_text_available=speech_to_text,
        text_to_speech_available=(
            shutil.which(settings.piper_binary) is not None
            and settings.piper_model_path is not None
            and settings.piper_model_path.is_file()
        ),
        telephone_provider=settings.telephone_provider,
        telephone_credentials_configured=request.app.state.calling_telephone.configured,
        telephone_live_calls_enabled=(
            request.app.state.calling_telephone.configured
            and request.app.state.calling_telephone.voice_stream_available
            and not settings.test_mode
            and ai_available
        ),
        test_mode=settings.test_mode,
        timezone=preferences.timezone,
        connected_clients=request.app.state.calling_hub.connected_clients,
    )


@router.get("/webrtc-config", response_model=list[IceServerResponse])
def webrtc_config(
    request: Request,
    _: Access,
) -> list[IceServerResponse]:
    settings: Settings = request.app.state.settings
    ice_servers = [IceServerResponse(urls=[server]) for server in settings.stun_servers]
    if settings.turn_server and settings.turn_username and settings.turn_credential:
        ice_servers.append(
            IceServerResponse(
                urls=[settings.turn_server],
                username=settings.turn_username.get_secret_value(),
                credential=settings.turn_credential.get_secret_value(),
            )
        )
    return ice_servers


@router.get("/schedules", response_model=list[ScheduleResponse])
def list_schedules(_: Access, db: Session = Depends(get_db)) -> list[CallSchedule]:
    return db.scalars(select(CallSchedule).order_by(CallSchedule.id)).all()


@router.put("/schedules/{schedule_id}", response_model=ScheduleResponse)
def update_schedule(
    schedule_id: str,
    payload: ScheduleUpdate,
    request: Request,
    _: Access,
    db: Session = Depends(get_db),
) -> CallSchedule:
    schedule = db.get(CallSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    schedule.local_time = payload.local_time
    schedule.enabled = payload.enabled
    schedule.updated_at = utc_now()
    db.commit()
    db.refresh(schedule)
    scheduler: CallScheduler = request.app.state.calling_scheduler
    scheduler.refresh()
    return schedule


@router.get("/preferences", response_model=PreferencesResponse)
def get_preferences(_: Access, db: Session = Depends(get_db)) -> CallingPreferences:
    preferences = db.get(CallingPreferences, 1)
    if preferences is None:
        raise HTTPException(status_code=503, detail="Calling preferences have not initialized.")
    return preferences


@router.put("/preferences", response_model=PreferencesResponse)
def update_preferences(
    payload: PreferencesUpdate,
    request: Request,
    _: Access,
    db: Session = Depends(get_db),
) -> CallingPreferences:
    try:
        ZoneInfo(payload.timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Unknown timezone.") from exc
    preferences = db.get(CallingPreferences, 1)
    if preferences is None:
        raise HTTPException(status_code=503, detail="Calling preferences have not initialized.")
    if payload.telephone_fallback_enabled and not payload.telephone_billing_confirmed:
        raise HTTPException(
            status_code=422,
            detail="Telephone fallback requires explicit billing confirmation.",
        )
    if payload.telephone_fallback_enabled and not request.app.state.calling_telephone.configured:
        raise HTTPException(
            status_code=409,
            detail="Configure the Twilio provider and HTTPS callback URL before enabling telephone fallback.",
        )
    if (
        payload.telephone_fallback_enabled
        and not request.app.state.calling_telephone.voice_stream_available
    ):
        raise HTTPException(
            status_code=409,
            detail="Install and configure local speech services before enabling telephone fallback.",
        )

    preferences.enabled = payload.enabled
    preferences.do_not_disturb = payload.do_not_disturb
    preferences.timezone = payload.timezone
    preferences.retry_limit = payload.retry_limit
    preferences.retry_delay_seconds = payload.retry_delay_seconds
    preferences.telephone_fallback_enabled = payload.telephone_fallback_enabled
    preferences.telephone_billing_confirmed = payload.telephone_billing_confirmed
    preferences.transcript_retention_enabled = payload.transcript_retention_enabled
    preferences.updated_at = utc_now()
    db.commit()
    db.refresh(preferences)
    scheduler: CallScheduler = request.app.state.calling_scheduler
    scheduler.refresh()
    return preferences


@router.get("/sessions", response_model=list[CallSessionResponse])
def list_sessions(
    _: Access,
    db: Session = Depends(get_db),
    limit: int = 50,
) -> list[CallSession]:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100.")
    return db.scalars(
        select(CallSession)
        .options(selectinload(CallSession.attempts))
        .order_by(CallSession.created_at.desc())
        .limit(limit)
    ).all()


@router.get("/sessions/{call_id}", response_model=CallSessionResponse)
def get_session(call_id: str, _: Access, db: Session = Depends(get_db)) -> CallSession:
    session = db.scalar(
        select(CallSession)
        .where(CallSession.id == call_id)
        .options(selectinload(CallSession.attempts))
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Call session not found.")
    return session


@router.websocket("/ws")
async def calling_websocket(websocket: WebSocket) -> None:
    settings: Settings = websocket.app.state.settings
    peer = websocket.client.host if websocket.client else "unknown"
    if settings.require_https and websocket.url.scheme != "wss":
        await websocket.close(code=1013, reason="Calling requires a secure WSS connection.")
        return
    if not settings.calling_auth_configured:
        await websocket.close(code=1013, reason="Calling authentication is not configured.")
        return
    if not websocket.app.state.calling_rate_limiter.allow(peer):
        await websocket.close(code=1013, reason="Calling connection rate limit exceeded.")
        return
    if not websocket_token_matches(websocket):
        await websocket.close(code=4401, reason="Invalid calling access token.")
        return

    await websocket.accept(subprotocol="jarvis.v1")
    hub = websocket.app.state.calling_hub
    await hub.connect(websocket)
    try:
        while True:
            raw_message = await websocket.receive_text()
            if len(raw_message) > 256_000:
                await websocket.send_json({"type": "error", "message": "Signaling message is too large."})
                continue
            try:
                message = decode_signal(raw_message)
                parsed = CallControlMessage.model_validate(message)
                result = await websocket.app.state.calling_manager.control_call(
                    parsed.model_dump()
                )
                await websocket.send_json(result)
            except (ValueError, ValidationError, TypeError) as exc:
                await websocket.send_json({"type": "error", "message": str(exc)[:240]})
            except Exception:
                logger.exception("Calling signaling request failed")
                await websocket.send_json(
                    {"type": "error", "message": "The signaling request could not be completed."}
                )
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(websocket)
