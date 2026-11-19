from datetime import date, datetime, time
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.conversation import utc_now


class CallingPreferences(Base):
    __tablename__ = "calling_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    do_not_disturb: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Africa/Nairobi", nullable=False)
    retry_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    retry_delay_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    telephone_fallback_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    telephone_billing_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    transcript_retention_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class CallSchedule(Base):
    __tablename__ = "call_schedules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    local_time: Mapped[time] = mapped_column(Time, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    prompt_context: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class CallSession(Base):
    __tablename__ = "call_sessions"
    __table_args__ = (
        UniqueConstraint("occurrence_key", name="uq_call_sessions_occurrence_key"),
        Index(
            "uq_call_sessions_single_active",
            text("(1)"),
            unique=True,
            sqlite_where=text("status IN ('queued', 'ringing', 'accepted', 'connecting', 'active')"),
            postgresql_where=text("status IN ('queued', 'ringing', 'accepted', 'connecting', 'active')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    occurrence_key: Mapped[str | None] = mapped_column(String(96), nullable=True)
    schedule_id: Mapped[str | None] = mapped_column(ForeignKey("call_schedules.id"), nullable=True)
    occurrence_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    channel: Mapped[str | None] = mapped_column(String(24), nullable=True)
    external_call_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcript: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    schedule: Mapped[CallSchedule | None] = relationship()
    attempts: Mapped[list["CallAttempt"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="CallAttempt.attempt_number"
    )


class CallAttempt(Base):
    __tablename__ = "call_attempts"
    __table_args__ = (
        UniqueConstraint("session_id", "attempt_number", name="uq_call_attempts_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("call_sessions.id", ondelete="CASCADE"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    result: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session: Mapped[CallSession] = relationship(back_populates="attempts")
