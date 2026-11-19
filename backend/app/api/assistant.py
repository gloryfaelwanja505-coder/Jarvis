import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.ollama_client import OllamaUnavailable
from app.actions.drafts import save_draft
from app.api.dependencies import get_db
from app.models import (
    AssistantAction,
    AssistantActionAudit,
    AssistantMemory,
    AssistantProfile,
)
from app.models.conversation import utc_now
from app.schemas.assistant import (
    ActionDraftCreate,
    ActionDraftResponse,
    MemoryCreate,
    MemoryResponse,
    ModelSelection,
    PersonalityUpdate,
)

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]


@router.get("/ai/status")
async def ai_status(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    manager = request.app.state.ai_manager
    if (
        hasattr(manager, "router")
        and settings.default_ai_provider is not None
        and settings.ai_provider not in {"openai", "groq"}
    ):
        return {
            **await manager.router.status(),
            "provider": manager.router.last_provider or settings.effective_ai_provider,
            "model": manager.router.model(manager.router.last_provider or "ollama"),
            "personality": manager.personality,
        }
    try:
        models = await manager.providers.local_models()
    except OllamaUnavailable:
        models = []
    return {
        "provider": settings.ai_provider,
        "available": settings.ai_provider == "ollama" and settings.ollama_model in models,
        "model": settings.ollama_model,
        "models": models,
        "personality": manager.personality,
    }


@router.get("/ai/providers")
async def ai_providers(request: Request) -> dict[str, object]:
    manager = request.app.state.ai_manager
    if not hasattr(manager, "router"):
        raise HTTPException(status_code=503, detail="AI provider management is unavailable.")
    return await manager.router.status()


@router.post("/ai/providers/{provider}/test")
async def test_ai_provider(provider: str, request: Request) -> dict[str, object]:
    manager = request.app.state.ai_manager
    if provider not in {"openai", "deepseek", "gemini", "ollama"} or not hasattr(manager, "router"):
        raise HTTPException(status_code=404, detail="Unknown AI provider.")
    if provider == "gemini":
        return await manager.router.gemini.test_connection()
    return await manager.router.health(provider)


@router.put("/ai/provider")
def select_ai_provider(payload: dict[str, str], request: Request) -> dict[str, str]:
    provider = payload.get("provider", "").lower().strip()
    if provider not in {"auto", "openai", "deepseek", "gemini", "ollama"}:
        raise HTTPException(status_code=422, detail="Choose auto, openai, deepseek, gemini, or ollama.")
    request.app.state.settings.default_ai_provider = provider
    return {"provider": provider}


@router.put("/ai/model")
async def select_ai_model(
    payload: ModelSelection,
    request: Request,
    db: Db,
) -> dict[str, str]:
    manager = request.app.state.ai_manager
    provider = payload.provider or request.app.state.settings.effective_ai_provider
    if provider == "gemini":
        models = await manager.router.gemini.list_models()
        if payload.model not in models:
            raise HTTPException(status_code=409, detail=f"Gemini model is not available: {payload.model}.")
        request.app.state.settings.gemini_model = payload.model
        return {"model": payload.model, "provider": "gemini"}
    if provider == "deepseek":
        request.app.state.settings.deepseek_model = payload.model
        return {"model": payload.model, "provider": "deepseek"}
    if provider != "ollama":
        raise HTTPException(status_code=409, detail="Model switching is available for Gemini and Ollama.")
    try:
        model = await manager.providers.select_local_model(payload.model)
    except OllamaUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    profile = db.get(AssistantProfile, 1)
    if profile is None:
        profile = AssistantProfile(id=1, selected_model=model, personality=manager.personality)
        db.add(profile)
    else:
        profile.selected_model = model
        profile.updated_at = utc_now()
    db.commit()
    return {"model": model}


@router.put("/ai/personality")
def update_personality(
    payload: PersonalityUpdate,
    request: Request,
    db: Db,
) -> dict[str, str]:
    personality = payload.personality.strip()
    if not personality:
        raise HTTPException(status_code=422, detail="Personality cannot be blank.")
    manager = request.app.state.ai_manager
    profile = db.get(AssistantProfile, 1)
    if profile is None:
        profile = AssistantProfile(
            id=1,
            selected_model=request.app.state.settings.ollama_model,
            personality=personality,
        )
        db.add(profile)
    else:
        profile.personality = personality
        profile.updated_at = utc_now()
    manager.personality = personality
    db.commit()
    return {"personality": personality}


@router.get("/memory", response_model=list[MemoryResponse])
def list_memories(db: Db) -> list[AssistantMemory]:
    return db.scalars(select(AssistantMemory).order_by(AssistantMemory.created_at)).all()


@router.post("/memory", response_model=MemoryResponse, status_code=201)
def save_memory(payload: MemoryCreate, db: Db) -> AssistantMemory:
    if not payload.approved:
        raise HTTPException(status_code=400, detail="A preference must be explicitly approved to save.")
    key = payload.key.strip()
    value = payload.value.strip()
    if not key or not value:
        raise HTTPException(status_code=422, detail="Preference name and value cannot be blank.")
    existing = db.scalar(select(AssistantMemory).where(AssistantMemory.key == key))
    if existing is None:
        memory = AssistantMemory(key=key, value=value, approved=True)
        db.add(memory)
    else:
        existing.value = value
        existing.approved = True
        existing.updated_at = utc_now()
        memory = existing
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That preference could not be saved.") from exc
    db.refresh(memory)
    return memory


@router.delete("/memory/{memory_id}", status_code=204)
def delete_memory(memory_id: int, db: Db) -> None:
    memory = db.get(AssistantMemory, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Saved preference not found.")
    db.delete(memory)
    db.commit()


@router.get("/actions", response_model=list[ActionDraftResponse])
def list_action_drafts(db: Db) -> list[AssistantAction]:
    return db.scalars(select(AssistantAction).order_by(AssistantAction.created_at.desc()).limit(50)).all()


@router.post("/actions/drafts", response_model=ActionDraftResponse, status_code=201)
def create_action_draft(payload: ActionDraftCreate, db: Db) -> AssistantAction:
    recipient = payload.recipient.strip()
    if payload.action_type == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", recipient):
        raise HTTPException(status_code=422, detail="Enter a valid email address for this draft.")
    if payload.action_type == "email" and not (payload.subject or "").strip():
        raise HTTPException(status_code=422, detail="Email drafts need a subject.")
    if not payload.body.strip():
        raise HTTPException(status_code=422, detail="Draft text cannot be blank.")
    return save_draft(db, payload)


@router.post("/actions/{action_id}/approve", response_model=ActionDraftResponse)
def approve_action(action_id: int, db: Db) -> AssistantAction:
    action = db.get(AssistantAction, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Draft not found.")
    if action.status != "draft":
        raise HTTPException(status_code=409, detail="This draft is no longer awaiting approval.")
    action.status = "approved_not_sent"
    action.updated_at = utc_now()
    db.add(
        AssistantActionAudit(
            action_id=action.id,
            event="approved_not_sent",
            detail="User approved this draft. No authorized delivery adapter is configured; nothing was sent.",
        )
    )
    db.commit()
    db.refresh(action)
    return action
