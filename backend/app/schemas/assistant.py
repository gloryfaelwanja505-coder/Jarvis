from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ModelSelection(BaseModel):
    model: str = Field(min_length=1, max_length=160)
    provider: str | None = Field(default=None, pattern="^(openai|deepseek|gemini|ollama)$")


class PersonalityUpdate(BaseModel):
    personality: str = Field(min_length=1, max_length=500)


class MemoryCreate(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=500)
    approved: bool


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    value: str
    approved: bool
    created_at: datetime


class ActionDraftCreate(BaseModel):
    action_type: str = Field(pattern="^(email|message)$")
    recipient: str = Field(min_length=1, max_length=320)
    subject: str | None = Field(default=None, max_length=300)
    body: str = Field(min_length=1, max_length=10_000)


class ActionDraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action_type: str
    recipient: str
    subject: str | None
    body: str
    status: str
    created_at: datetime
