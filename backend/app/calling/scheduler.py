from datetime import datetime
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.calling.call_manager import CallManager
from app.models import CallSchedule, CallSession, CallingPreferences

logger = logging.getLogger(__name__)

DEFAULT_SCHEDULES = (
    ("morning", "07:00", "morning"),
    ("evening", "17:00", "evening"),
)


def ensure_calling_defaults(session_factory: sessionmaker[Session], timezone_name: str) -> None:
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown calling timezone: {timezone_name}") from exc
    with session_factory.begin() as db:
        if db.get(CallingPreferences, 1) is None:
            db.add(CallingPreferences(id=1, timezone=timezone_name))
        for schedule_id, local_time, context in DEFAULT_SCHEDULES:
            if db.get(CallSchedule, schedule_id) is None:
                db.add(
                    CallSchedule(
                        id=schedule_id,
                        local_time=datetime.strptime(local_time, "%H:%M").time(),
                        enabled=True,
                        prompt_context=context,
                    )
                )


class CallScheduler:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        manager: CallManager,
    ) -> None:
        self.session_factory = session_factory
        self.manager = manager
        self.scheduler = AsyncIOScheduler()

    @property
    def running(self) -> bool:
        return self.scheduler.running

    async def start(self) -> None:
        self.manager.recover_interrupted_sessions()
        self.scheduler.start()
        self.record_missed_occurrences()
        self.refresh()

    def record_missed_occurrences(self, now: datetime | None = None) -> None:
        with self.session_factory.begin() as db:
            preferences = db.get(CallingPreferences, 1)
            if preferences is None or not preferences.enabled:
                return
            timezone = ZoneInfo(preferences.timezone)
            local_now = (now or datetime.now(timezone)).astimezone(timezone)
            schedules = db.scalars(
                select(CallSchedule).where(CallSchedule.enabled.is_(True))
            ).all()
            for schedule in schedules:
                if schedule.local_time > local_now.time().replace(tzinfo=None):
                    continue
                occurrence_date = local_now.date()
                occurrence_key = f"{schedule.id}:{occurrence_date.isoformat()}"
                if db.scalar(
                    select(CallSession.id).where(
                        CallSession.occurrence_key == occurrence_key
                    )
                ):
                    continue
                do_not_disturb = preferences.do_not_disturb
                db.add(
                    CallSession(
                        occurrence_key=occurrence_key,
                        schedule_id=schedule.id,
                        occurrence_date=occurrence_date,
                        status="skipped" if do_not_disturb else "missed",
                        outcome=(
                            "do_not_disturb"
                            if do_not_disturb
                            else "backend_unavailable_at_scheduled_time"
                        ),
                    )
                )

    def refresh(self) -> None:
        with self.session_factory() as db:
            preferences = db.get(CallingPreferences, 1)
            schedules = db.scalars(select(CallSchedule)).all()
            timezone_name = preferences.timezone if preferences else "Africa/Nairobi"
        try:
            timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            logger.exception("Could not load calling timezone %s", timezone_name)
            raise ValueError(f"Unknown calling timezone: {timezone_name}") from exc

        active_ids = set()
        for schedule in schedules:
            if not schedule.enabled:
                continue
            active_ids.add(schedule.id)
            self.scheduler.add_job(
                self.manager.run_scheduled,
                trigger=CronTrigger(
                    hour=schedule.local_time.hour,
                    minute=schedule.local_time.minute,
                    timezone=timezone,
                ),
                args=[schedule.id],
                id=f"calling-{schedule.id}",
                name=f"JARVIS {schedule.id} call",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=600,
            )
        for job in self.scheduler.get_jobs():
            if job.id.startswith("calling-") and job.id.removeprefix("calling-") not in active_ids:
                self.scheduler.remove_job(job.id)

    async def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
