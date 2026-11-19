from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ScheduleUpdate(BaseModel):
    local_time: time
    enabled: bool

    @field_validator("local_time")
    @classmethod
    def minute_precision(cls, value: time) -> time:
        if value.second or value.microsecond:
            raise ValueError("Schedules support minute precision.")
        return value


class PreferencesUpdate(BaseModel):
    enabled: bool
    do_not_disturb: bool
    timezone: str = Field(min_length=1, max_length=64)
    retry_limit: int = Field(ge=0, le=5)
    retry_delay_seconds: int = Field(ge=60, le=86400)
    telephone_fallback_enabled: bool = False
    telephone_billing_confirmed: bool = False
    transcript_retention_enabled: bool = False


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    local_time: time
    enabled: bool
    prompt_context: str


class PreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool
    do_not_disturb: bool
    timezone: str
    retry_limit: int
    retry_delay_seconds: int
    telephone_fallback_enabled: bool
    telephone_billing_confirmed: bool
    transcript_retention_enabled: bool


class CallingStatusResponse(BaseModel):
    authentication_configured: bool
    scheduler_running: bool
    ai_provider: str
    ai_available: bool
    webrtc_signaling_available: bool
    webrtc_media_available: bool
    speech_to_text_available: bool
    text_to_speech_available: bool
    telephone_provider: str
    telephone_credentials_configured: bool
    telephone_live_calls_enabled: bool
    test_mode: bool
    timezone: str
    connected_clients: int


class IceServerResponse(BaseModel):
    urls: list[str]
    username: str | None = None
    credential: str | None = None


class CallAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    attempt_number: int
    channel: str
    status: str
    result: str | None
    created_at: datetime
    completed_at: datetime | None


class CallSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    schedule_id: str | None
    occurrence_date: date | None
    status: str
    channel: str | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    transcript: str
    summary: str
    outcome: str | None
    created_at: datetime
    attempts: list[CallAttemptResponse]


class CallControlMessage(BaseModel):
    type: Literal["answer", "decline", "end", "offer", "answer_sdp", "ice_candidate", "status"]
    call_id: str = Field(min_length=36, max_length=36)
    payload: dict[str, object] = Field(default_factory=dict, max_length=32)

    @model_validator(mode="after")
    def validate_signaling_payload(self) -> "CallControlMessage":
        if self.type == "offer":
            sdp = self.payload.get("sdp")
            if not isinstance(sdp, str) or not sdp.startswith("v=") or len(sdp) > 250_000:
                raise ValueError("A valid bounded SDP offer is required.")
        if self.type == "ice_candidate":
            candidate = self.payload.get("candidate")
            if (
                not isinstance(candidate, str)
                or not candidate.startswith("candidate:")
                or len(candidate) > 2_000
            ):
                raise ValueError("A valid bounded ICE candidate is required.")
        return self
