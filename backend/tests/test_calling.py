from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.calling.retry_manager import planned_attempts
from app.calling.scheduler import CallScheduler, ensure_calling_defaults
from app.calling.audio.voice_activity import VoiceActivityDetector
from app.calling.call_memory import append_transcript
from app.models import CallSchedule


def test_default_schedule_times_and_timezone(client) -> None:
    session_factory = client.app.state.session_factory
    with session_factory() as db:
        morning = db.get(CallSchedule, "morning")
        evening = db.get(CallSchedule, "evening")
        preferences = db.get(__import__("app.models", fromlist=["CallingPreferences"]).CallingPreferences, 1)

    assert morning.local_time.strftime("%H:%M") == "07:00"
    assert evening.local_time.strftime("%H:%M") == "17:00"
    assert preferences.timezone == "Africa/Nairobi"


def test_scheduler_uses_nairobi_wall_clock(client) -> None:
    scheduler: CallScheduler = client.app.state.calling_scheduler
    morning = next(job for job in scheduler.scheduler.get_jobs() if job.id == "calling-morning")
    next_run = morning.trigger.get_next_fire_time(None, datetime(2026, 11, 10, 0, 0, tzinfo=ZoneInfo("UTC")))

    assert next_run is not None
    assert next_run.astimezone(ZoneInfo("Africa/Nairobi")).hour == 7


def test_scheduler_records_calls_missed_while_backend_was_offline(client) -> None:
    from datetime import date
    from app.models import CallSession, CallingPreferences

    with client.app.state.session_factory() as db:
        db.get(CallingPreferences, 1).enabled = True
        db.commit()
    scheduler: CallScheduler = client.app.state.calling_scheduler
    scheduler.record_missed_occurrences(
        datetime(2026, 11, 10, 18, 0, tzinfo=ZoneInfo("Africa/Nairobi"))
    )

    with client.app.state.session_factory() as db:
        missed = db.query(CallSession).filter_by(
            occurrence_date=date(2026, 11, 10),
            status="missed",
        ).all()
    assert len(missed) == 2
    assert {item.outcome for item in missed} == {
        "backend_unavailable_at_scheduled_time"
    }


def test_duplicate_daily_occurrence_is_idempotent(client) -> None:
    from datetime import date, datetime, timezone
    from app.models import CallSession, CallingPreferences
    import asyncio

    manager = client.app.state.calling_manager.router
    with client.app.state.session_factory() as db:
        db.get(CallingPreferences, 1).retry_limit = 0
        db.commit()
    first = asyncio.run(
        manager.run_schedule("morning", datetime(2026, 11, 10, 4, 0, tzinfo=timezone.utc))
    )
    second = asyncio.run(
        manager.run_schedule("morning", datetime(2026, 11, 10, 5, 0, tzinfo=timezone.utc))
    )

    assert first.id == second.id
    with client.app.state.session_factory() as db:
        assert db.query(CallSession).filter_by(occurrence_date=date(2026, 11, 10)).count() == 1


def test_overlapping_schedule_is_recorded_without_starting_another_call(client) -> None:
    from datetime import datetime, timezone
    import asyncio

    from app.models import CallSession
    from app.models.conversation import utc_now

    with client.app.state.session_factory() as db:
        db.add(CallSession(id="ongoing-call", status="active", started_at=utc_now()))
        db.commit()

    session = asyncio.run(
        client.app.state.calling_manager.router.run_schedule(
            "morning",
            datetime(2026, 11, 10, 4, 0, tzinfo=timezone.utc),
        )
    )

    assert session.status == "skipped"
    assert session.outcome == "another_call_active:ongoing-call"


def test_call_router_retries_unanswered_internet_channel(client, monkeypatch) -> None:
    from datetime import datetime, timezone
    import asyncio

    from unittest.mock import AsyncMock

    from app.models import CallAttempt, CallingPreferences

    router = client.app.state.calling_manager.router
    router.webrtc = type("UnavailableWebRTC", (), {"media_available": False})()
    router.conversation_engine.is_available = AsyncMock(return_value=True)
    monkeypatch.setattr("app.calling.call_routing.asyncio.sleep", AsyncMock())
    with client.app.state.session_factory() as db:
        preferences = db.get(CallingPreferences, 1)
        preferences.enabled = True
        preferences.retry_limit = 1
        db.commit()

    session = asyncio.run(
        router.run_schedule(
            "morning",
            datetime(2026, 11, 10, 4, 0, tzinfo=timezone.utc),
        )
    )

    assert session.status == "missed"
    with client.app.state.session_factory() as db:
        attempts = db.query(CallAttempt).filter_by(session_id=session.id).all()
    assert len(attempts) == 2
    assert all(attempt.status == "failed" for attempt in attempts)


def test_call_router_uses_explicitly_enabled_telephone_fallback(client) -> None:
    from datetime import datetime, timezone
    import asyncio
    from unittest.mock import AsyncMock

    from app.models import CallAttempt, CallingPreferences

    class TestTelephone:
        configured = True
        voice_stream_available = True

        place_call = AsyncMock(return_value="CA123")

    router = client.app.state.calling_manager.router
    router.settings = router.settings.model_copy(update={"test_mode": False})
    router.webrtc = type("UnavailableWebRTC", (), {"media_available": False})()
    router.telephone = TestTelephone()
    router.conversation_engine.is_available = AsyncMock(return_value=True)
    with client.app.state.session_factory() as db:
        preferences = db.get(CallingPreferences, 1)
        preferences.enabled = True
        preferences.retry_limit = 0
        preferences.telephone_fallback_enabled = True
        preferences.telephone_billing_confirmed = True
        db.commit()

    session = asyncio.run(
        router.run_schedule(
            "morning",
            datetime(2026, 11, 10, 4, 0, tzinfo=timezone.utc),
        )
    )

    assert session.status == "ringing"
    assert session.channel == "telephone"
    assert session.external_call_id == "CA123"
    router.telephone.place_call.assert_awaited_once()
    with client.app.state.session_factory() as db:
        attempts = db.query(CallAttempt).filter_by(session_id=session.id).all()
    assert [(attempt.channel, attempt.status) for attempt in attempts] == [
        ("webrtc", "failed"),
        ("telephone", "ringing"),
    ]


def test_uncertain_telephone_result_is_not_retried(client) -> None:
    from datetime import datetime, timezone
    import asyncio
    from unittest.mock import AsyncMock

    from app.calling.providers.telephone import TelephoneCallUncertain
    from app.models import CallAttempt, CallingPreferences

    class UncertainTelephone:
        configured = True
        voice_stream_available = True

        place_call = AsyncMock(
            side_effect=TelephoneCallUncertain("Provider response timed out.")
        )

    router = client.app.state.calling_manager.router
    router.settings = router.settings.model_copy(update={"test_mode": False})
    router.webrtc = type("UnavailableWebRTC", (), {"media_available": False})()
    router.telephone = UncertainTelephone()
    router.conversation_engine.is_available = AsyncMock(return_value=True)
    with client.app.state.session_factory() as db:
        preferences = db.get(CallingPreferences, 1)
        preferences.enabled = True
        preferences.retry_limit = 2
        preferences.telephone_fallback_enabled = True
        preferences.telephone_billing_confirmed = True
        db.commit()

    session = asyncio.run(
        router.run_schedule(
            "morning",
            datetime(2026, 11, 10, 4, 0, tzinfo=timezone.utc),
        )
    )

    assert session.status == "unknown"
    assert session.channel == "telephone"
    assert "no retry" in session.outcome.lower()
    router.telephone.place_call.assert_awaited_once()
    with client.app.state.session_factory() as db:
        attempts = db.query(CallAttempt).filter_by(session_id=session.id).all()
    assert [(attempt.channel, attempt.status) for attempt in attempts] == [
        ("webrtc", "failed"),
        ("telephone", "uncertain"),
    ]


def test_opted_in_transcripts_redact_credentials(client) -> None:
    from app.models import CallSession, CallingPreferences

    with client.app.state.session_factory() as db:
        db.get(CallingPreferences, 1).transcript_retention_enabled = True
        session = CallSession(id="transcript-call", status="completed")
        db.add(session)
        db.commit()
        append_transcript(
            db,
            session,
            "owner",
            "My password=hunter2 and api_key=sk-abcdefghijklmnopqrstuvwxyz123456",
        )
        assert "hunter2" not in session.transcript
        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in session.transcript
        assert session.transcript.count("[REDACTED]") == 2


def test_retry_plan_orders_channels_before_retries() -> None:
    assert planned_attempts(1, ["webrtc", "telephone"]) == [
        (1, "webrtc"),
        (2, "telephone"),
        (3, "webrtc"),
        (4, "telephone"),
    ]
    with pytest.raises(ValueError):
        planned_attempts(-1, ["webrtc"])


def test_voice_activity_detects_voice_after_silence() -> None:
    detector = VoiceActivityDetector(
        sample_rate=16_000,
        threshold=0.01,
        silence_seconds=0.02,
        minimum_speech_seconds=0.01,
    )
    speech = (b"\x00\x40" * 320)

    assert detector.process(speech) is None
    phrase = detector.process(bytes(640))

    assert phrase is not None
    assert len(phrase) == len(speech) + 640


def test_voice_activity_caps_unbroken_speech_buffer() -> None:
    detector = VoiceActivityDetector(
        sample_rate=16_000,
        threshold=0.01,
        minimum_speech_seconds=0.01,
        maximum_speech_seconds=0.02,
    )
    speech = b"\x00\x40" * 320

    phrase = detector.process(speech)

    assert phrase == speech
    assert detector.flush() is None
