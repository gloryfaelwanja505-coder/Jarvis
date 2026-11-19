import json
import logging
from collections.abc import AsyncIterator

import httpx
from fastapi import HTTPException, status
from openai import AsyncOpenAI
from pydantic import SecretStr

from app.config import Settings

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTIONS = (
    "You are JARVIS, a capable personal AI assistant. Be warm, natural, confident, "
    "and concise when the question is simple; be thorough when the subject requires it. "
    "Use dry wit sparingly when it suits the conversation, never at the user's expense. "
    "You cannot operate the user's computer and have no tools for sending messages, "
    "emails, or initiating calls. Never claim that you performed an external action. "
    "If asked to do something you cannot actually do, say so plainly and offer to help "
    "draft, plan, or explain the next step."
)
AI_REQUEST_TIMEOUT_SECONDS = 90


class AIProviderError(RuntimeError):
    pass


def create_openai_client(api_key: SecretStr | None) -> AsyncOpenAI:
    if api_key is None or not api_key.get_secret_value().strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI is not configured. Set OPENAI_API_KEY in backend/.env.",
        )
    return AsyncOpenAI(
        api_key=api_key.get_secret_value(),
        timeout=AI_REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )


def response_input(messages: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"role": role, "content": content} for role, content in messages]


def configured_model(settings: Settings) -> str:
    if settings.ai_provider == "ollama":
        return settings.ollama_model
    return settings.openai_model


def chat_provider(settings: Settings) -> str:
    return "ollama" if settings.ai_provider == "ollama" else "openai"


def ai_is_configured(settings: Settings) -> bool:
    if chat_provider(settings) == "ollama":
        return bool(settings.ollama_base_url.strip() and settings.ollama_model.strip())
    return (
        settings.openai_api_key is not None
        and bool(settings.openai_api_key.get_secret_value().strip())
    )


def _ollama_payload(
    settings: Settings,
    messages: list[tuple[str, str]],
    stream: bool,
) -> dict[str, object]:
    return {
        "model": settings.ollama_model,
        "stream": stream,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            *[{"role": role, "content": content} for role, content in messages],
        ],
        "options": {"temperature": 0.7},
    }


async def ollama_chat(
    settings: Settings,
    messages: list[tuple[str, str]],
) -> str:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    try:
        async with httpx.AsyncClient(timeout=AI_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                json=_ollama_payload(settings, messages, stream=False),
            )
            response.raise_for_status()
            body = response.json()
            content = body["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("Ollama returned non-text content.")
            return content
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        logger.exception("Ollama chat request failed")
        raise AIProviderError("Ollama could not complete the request.") from exc


async def stream_ollama_chat(
    settings: Settings,
    messages: list[tuple[str, str]],
) -> AsyncIterator[str]:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    try:
        async with httpx.AsyncClient(timeout=AI_REQUEST_TIMEOUT_SECONDS) as client:
            async with client.stream(
                "POST",
                url,
                json=_ollama_payload(settings, messages, stream=True),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    body = json.loads(line)
                    if not isinstance(body, dict):
                        raise TypeError("Ollama returned an invalid response chunk.")
                    if "error" in body:
                        raise AIProviderError("Ollama could not complete the request.")
                    message = body.get("message", {})
                    content = message.get("content", "") if isinstance(message, dict) else ""
                    if content:
                        if not isinstance(content, str):
                            raise TypeError("Ollama returned non-text content.")
                        yield content
                    if body.get("done") is True:
                        return
                raise AIProviderError("Ollama ended the response before completion.")
    except AIProviderError:
        raise
    except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.exception("Ollama chat stream failed")
        raise AIProviderError("Ollama could not complete the request.") from exc
