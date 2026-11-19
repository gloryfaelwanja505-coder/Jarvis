from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, min_length=36, max_length=36)
    task_id: str | None = Field(default=None, min_length=36, max_length=36)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message cannot be blank.")
        return cleaned


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    created_at: datetime


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class AssistantTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_message_id: str
    status: str
    stage: str
    attempt_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class ConversationResponse(ConversationSummary):
    messages: list[MessageResponse]
    tasks: list[AssistantTaskResponse] = Field(default_factory=list)


class ChatResponse(BaseModel):
    conversation_id: str
    message: MessageResponse
    model: str
