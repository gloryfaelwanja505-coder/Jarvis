import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
import httpx
from openai import OpenAIError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.api.dependencies import get_db
from app.config import Settings
from app.models import AssistantTask, AssistantTaskCheckpoint, Conversation, Message
from app.models.conversation import utc_now
from app.schemas.chat import (
    AssistantTaskResponse,
    ChatRequest,
    ChatResponse,
    ConversationResponse,
    ConversationSummary,
    MessageResponse,
)
from app.services.ai import (
    AI_REQUEST_TIMEOUT_SECONDS,
    AIProviderError,
    SYSTEM_INSTRUCTIONS,
    configured_model,
    create_openai_client,
    response_input,
)
from app.ai.personality import system_prompt
from app.ai.router import ProviderError

logger = logging.getLogger(__name__)
router = APIRouter()
HISTORY_LIMIT = 20
CHAT_TIMEOUT_SECONDS = AI_REQUEST_TIMEOUT_SECONDS
MAX_TASK_ATTEMPTS = 2
ACTIVE_TASK_STATES = ("queued", "running")


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def add_checkpoint(db: Session, task: AssistantTask, stage: str, detail: str) -> None:
    latest = db.scalar(
        select(func.max(AssistantTaskCheckpoint.checkpoint_number)).where(
            AssistantTaskCheckpoint.task_id == task.id
        )
    )
    db.add(
        AssistantTaskCheckpoint(
            id=str(uuid4()),
            task_id=task.id,
            checkpoint_number=(latest or 0) + 1,
            stage=stage,
            detail=detail[:160],
        )
    )
    task.stage = stage
    task.updated_at = utc_now()


def recover_interrupted_tasks(
    session_factory: sessionmaker[Session],
    detail: str = "JARVIS restarted before this response was saved. No action was replayed.",
) -> None:
    with session_factory.begin() as db:
        tasks = db.scalars(
            select(AssistantTask).where(AssistantTask.status.in_(ACTIVE_TASK_STATES))
        ).all()
        for task in tasks:
            task.status = "interrupted"
            task.error_message = detail
            add_checkpoint(db, task, "interrupted", detail)
        if tasks:
            logger.warning("Marked %d unfinished assistant task(s) as interrupted", len(tasks))


def begin_task(
    db: Session,
    payload: ChatRequest,
) -> tuple[AssistantTask, Conversation, list[tuple[str, str]], Message | None]:
    try:
        task_id = str(UUID(payload.task_id)) if payload.task_id else str(uuid4())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid task_id.") from exc

    request_hash = hashlib.sha256(payload.message.encode("utf-8")).hexdigest()
    existing_task = db.get(AssistantTask, task_id)
    if existing_task is not None:
        user_message = db.get(Message, existing_task.user_message_id)
        if (
            user_message is None
            or existing_task.request_hash != request_hash
            or (payload.conversation_id and payload.conversation_id != existing_task.conversation_id)
        ):
            raise HTTPException(status_code=409, detail="This request ID belongs to a different message.")
        conversation = db.get(Conversation, existing_task.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=410, detail="The conversation for this request no longer exists.")
        if existing_task.status == "completed":
            assistant_message = (
                db.get(Message, existing_task.assistant_message_id)
                if existing_task.assistant_message_id
                else None
            )
            if assistant_message is None:
                raise HTTPException(status_code=500, detail="The saved response is unavailable.")
            return existing_task, conversation, [], assistant_message
        if existing_task.status in ACTIVE_TASK_STATES:
            raise HTTPException(status_code=409, detail="This response is already being generated.")
        if existing_task.status not in {"interrupted", "failed"}:
            raise HTTPException(status_code=409, detail="This request cannot be retried.")
        if existing_task.attempt_count >= MAX_TASK_ATTEMPTS:
            raise HTTPException(
                status_code=409,
                detail="This response has already been retried. Send a new message to try again.",
            )

        recent = db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(HISTORY_LIMIT + 1)
        ).all()
        history = [
            (message.role, message.content)
            for message in reversed(recent)
            if message.id != user_message.id
        ][-HISTORY_LIMIT:]
        existing_task.status = "running"
        existing_task.error_message = None
        existing_task.completed_at = None
        existing_task.attempt_count += 1
        add_checkpoint(db, existing_task, "retrying", "Retry requested by the user.")
        db.commit()
        return existing_task, conversation, [*history, ("user", user_message.content)], None

    if payload.conversation_id is None:
        conversation = Conversation(title=payload.message[:120])
        db.add(conversation)
        db.flush()
    else:
        try:
            UUID(payload.conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid conversation_id.") from exc
        conversation = db.get(Conversation, payload.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")

    recent = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    history = [(message.role, message.content) for message in reversed(recent)]
    user_message = Message(
        id=str(uuid4()),
        conversation_id=conversation.id,
        role="user",
        content=payload.message,
    )
    task = AssistantTask(
        id=task_id,
        conversation_id=conversation.id,
        user_message_id=user_message.id,
        request_hash=request_hash,
        status="running",
        stage="generating",
        attempt_count=1,
    )
    db.add_all([user_message, task])
    db.flush()
    conversation.updated_at = user_message.created_at
    add_checkpoint(db, task, "generating", "Message saved; waiting for the AI response.")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This request is already being handled.") from exc
    return task, conversation, [*history, ("user", payload.message)], None


def save_response(
    db: Session,
    task: AssistantTask,
    conversation_id: str,
    content: str,
) -> Message:
    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=content,
        created_at=utc_now(),
    )
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise RuntimeError("Conversation disappeared before the response could be saved.")
    conversation.updated_at = assistant_message.created_at
    db.add(assistant_message)
    db.flush()
    task.assistant_message_id = assistant_message.id
    task.status = "completed"
    task.error_message = None
    task.completed_at = assistant_message.created_at
    add_checkpoint(db, task, "completed", "Response saved to conversation history.")
    db.commit()
    db.refresh(assistant_message)
    return assistant_message


def fail_task(db: Session, task_id: str, detail: str, stage: str = "failed") -> None:
    task = db.get(AssistantTask, task_id)
    if task is None or task.status == "completed":
        return
    task.status = "failed" if stage == "failed" else "interrupted"
    task.error_message = detail[:500]
    task.completed_at = utc_now()
    add_checkpoint(db, task, stage, detail)
    db.commit()


def task_meta(task: AssistantTask, conversation_id: str, model: str) -> str:
    data = {
        "conversation_id": conversation_id,
        "task_id": task.id,
        "user_message_id": task.user_message_id,
        "attempt_count": task.attempt_count,
        "model": model,
    }
    return f"event: meta\ndata: {json.dumps(data)}\n\n"


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    use_router = (
        hasattr(request.app.state.ai_manager, "router")
        and settings.default_ai_provider is not None
        and settings.ai_provider not in {"openai", "groq"}
    )
    client = None if settings.ai_provider == "ollama" or use_router else create_openai_client(settings.openai_api_key)
    task, conversation, messages, saved_response = begin_task(db, payload)
    model = configured_model(settings)
    if saved_response is not None:
        return ChatResponse(
            conversation_id=conversation.id,
            message=MessageResponse.model_validate(saved_response),
            model=model,
        )
    approved_preferences = request.app.state.ai_context.approved_preferences(db)
    try:
        async with asyncio.timeout(CHAT_TIMEOUT_SECONDS):
            if use_router:
                content, model = await request.app.state.ai_manager.router.generate(
                    [{"role": role, "content": value} for role, value in messages],
                    system_prompt(request.app.state.ai_manager.personality, approved_preferences),
                    settings.effective_ai_provider,
                )
            elif settings.ai_provider == "ollama":
                content = await request.app.state.ai_manager.generate(
                    messages,
                    approved_preferences,
                )
            else:
                assert client is not None
                async with client:
                    response = await client.responses.create(
                        model=model,
                        instructions=system_prompt(
                            request.app.state.ai_manager.personality,
                            approved_preferences,
                        ),
                        input=response_input(messages),
                    )
                content = response.output_text.strip()
    except TimeoutError as exc:
        fail_task(db, task.id, "The AI service took too long to respond.")
        raise HTTPException(status_code=504, detail="JARVIS took too long to respond. You can retry this message.") from exc
    except AIProviderError as exc:
        logger.exception("Local AI request failed for task %s", task.id)
        detail = "Ollama couldn't finish that response. Check that it's running and the model is available."
        fail_task(db, task.id, detail)
        raise HTTPException(status_code=502, detail=detail) from exc
    except ProviderError as exc:
        logger.warning("AI router failed for task %s: %s", task.id, exc)
        detail = str(exc)
        fail_task(db, task.id, detail)
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        logger.exception("AI provider request failed for task %s", task.id)
        fail_task(db, task.id, "The AI service could not complete the request.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI service could not complete the request.",
        ) from exc
    except OpenAIError as exc:
        logger.exception("OpenAI Responses API request failed for task %s", task.id)
        fail_task(db, task.id, "The AI service could not complete the request.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI service could not complete the request.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error while generating response for task %s", task.id)
        db.rollback()
        fail_task(db, task.id, "Something went wrong before the response could be saved.")
        raise HTTPException(
            status_code=502,
            detail="JARVIS couldn't finish that response. You can retry it from the conversation.",
        ) from exc

    try:
        content = content.strip()
        if not content:
            fail_task(db, task.id, "The AI service returned an empty response.")
            raise HTTPException(status_code=502, detail="The AI service returned an empty response.")
        assistant_message = save_response(db, task, conversation.id, content)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Could not save response for task %s", task.id)
        db.rollback()
        fail_task(db, task.id, "The response could not be saved to conversation history.")
        raise HTTPException(
            status_code=500,
            detail="I couldn't save that response. Please retry it from the conversation.",
        ) from exc
    return ChatResponse(
        conversation_id=conversation.id,
        message=MessageResponse.model_validate(assistant_message),
        model=model,
    )


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    use_router = (
        hasattr(request.app.state.ai_manager, "router")
        and settings.default_ai_provider is not None
        and settings.ai_provider not in {"openai", "groq"}
    )
    client = None if settings.ai_provider == "ollama" or use_router else create_openai_client(settings.openai_api_key)
    task, conversation, messages, saved_response = begin_task(db, payload)
    conversation_id = conversation.id
    model = configured_model(settings)
    approved_preferences = request.app.state.ai_context.approved_preferences(db)

    async def events() -> AsyncIterator[str]:
        chunks: list[str] = []
        model = configured_model(settings)
        try:
            yield task_meta(task, conversation_id, model)
            if saved_response is not None:
                yield f"event: delta\ndata: {json.dumps({'text': saved_response.content})}\n\n"
                yield f"event: done\ndata: {json.dumps({'conversation_id': conversation_id, 'task_id': task.id})}\n\n"
                return

            async with asyncio.timeout(CHAT_TIMEOUT_SECONDS):
                if use_router:
                    async for delta, stream_model in request.app.state.ai_manager.router.stream(
                        [{"role": role, "content": value} for role, value in messages],
                        system_prompt(request.app.state.ai_manager.personality, approved_preferences),
                        settings.effective_ai_provider,
                    ):
                        model = stream_model
                        chunks.append(delta)
                        yield f"event: delta\ndata: {json.dumps({'text': delta})}\n\n"
                elif settings.ai_provider == "ollama":
                    async for delta in request.app.state.ai_manager.stream(
                        messages,
                        approved_preferences,
                    ):
                        chunks.append(delta)
                        yield f"event: delta\ndata: {json.dumps({'text': delta})}\n\n"
                else:
                    assert client is not None
                    async with client:
                        stream = await client.responses.create(
                            model=model,
                            instructions=system_prompt(
                                request.app.state.ai_manager.personality,
                                approved_preferences,
                            ),
                            input=response_input(messages),
                            stream=True,
                        )
                        async for event in stream:
                            if event.type == "response.output_text.delta":
                                chunks.append(event.delta)
                                yield f"event: delta\ndata: {json.dumps({'text': event.delta})}\n\n"

            content = "".join(chunks).strip()
            if not content:
                detail = "The AI service returned an empty response."
                logger.error("OpenAI Responses API stream returned no text for task %s", task.id)
                fail_task(db, task.id, detail)
                yield f"event: error\ndata: {json.dumps({'message': detail})}\n\n"
                return

            save_response(db, task, conversation_id, content)
            yield f"event: done\ndata: {json.dumps({'conversation_id': conversation_id, 'task_id': task.id})}\n\n"
        except TimeoutError:
            detail = "The AI service took too long to respond. You can retry this message."
            db.rollback()
            fail_task(db, task.id, detail)
            yield f"event: error\ndata: {json.dumps({'message': detail})}\n\n"
        except OpenAIError:
            logger.exception("OpenAI Responses API stream failed for task %s", task.id)
            detail = "The AI service could not complete the request."
            db.rollback()
            fail_task(db, task.id, detail)
            yield f"event: error\ndata: {json.dumps({'message': detail})}\n\n"
        except ProviderError as exc:
            detail = str(exc)
            fail_task(db, task.id, detail)
            yield f"event: error\ndata: {json.dumps({'message': detail})}\n\n"
        except AIProviderError:
            logger.exception("Local AI stream failed for task %s", task.id)
            detail = "Ollama couldn't finish that response. Check that it's running and the model is available."
            db.rollback()
            fail_task(db, task.id, detail)
            yield f"event: error\ndata: {json.dumps({'message': detail})}\n\n"
        except httpx.HTTPError:
            logger.exception("AI provider stream failed for task %s", task.id)
            detail = "The AI service could not complete the request."
            db.rollback()
            fail_task(db, task.id, detail)
            yield f"event: error\ndata: {json.dumps({'message': detail})}\n\n"
        except asyncio.CancelledError:
            db.rollback()
            fail_task(db, task.id, "The response was interrupted before it could be saved.", "interrupted")
            raise
        except Exception:
            logger.exception("Unexpected error while generating response for task %s", task.id)
            db.rollback()
            fail_task(db, task.id, "Something went wrong before the response could be saved.")
            yield f"event: error\ndata: {json.dumps({'message': 'Something went wrong before the response could be saved. You can retry this message.'})}\n\n"
        finally:
            db.close()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(db: Session = Depends(get_db)) -> list[Conversation]:
    return db.scalars(
        select(Conversation).order_by(Conversation.updated_at.desc()).limit(50)
    ).all()


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
) -> ConversationResponse:
    try:
        UUID(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid conversation_id.") from exc
    conversation = db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    tasks = db.scalars(
        select(AssistantTask)
        .where(AssistantTask.conversation_id == conversation.id)
        .order_by(AssistantTask.created_at.desc(), AssistantTask.id.desc())
    ).all()
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[MessageResponse.model_validate(message) for message in conversation.messages],
        tasks=[AssistantTaskResponse.model_validate(task) for task in tasks],
    )
