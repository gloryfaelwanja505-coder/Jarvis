import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class OllamaUnavailable(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def base_url(self) -> str:
        return self.settings.ollama_base_url.rstrip("/")

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
            body = response.json()
            models = body.get("models", []) if isinstance(body, dict) else []
            if not isinstance(models, list):
                raise OllamaUnavailable("Ollama returned an invalid model list.")
            return sorted(
                {
                    str(model["name"])
                    for model in models
                    if isinstance(model, dict)
                    and isinstance(model.get("name"), str)
                    and model["name"]
                }
            )
        except (httpx.HTTPError, ValueError, OllamaUnavailable) as exc:
            logger.info("Ollama model discovery failed: %s", exc)
            raise OllamaUnavailable("Ollama is unavailable.") from exc

    async def generate(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> str:
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": model or self.settings.ollama_model,
                        "stream": False,
                        "messages": messages,
                        "options": {"temperature": 0.7},
                    },
                )
                response.raise_for_status()
            body = response.json()
            message = body.get("message", {}) if isinstance(body, dict) else {}
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str):
                raise OllamaUnavailable("Ollama returned an invalid response.")
            return content
        except (httpx.HTTPError, ValueError, OllamaUnavailable) as exc:
            logger.exception("Ollama generation failed")
            raise OllamaUnavailable("Ollama could not complete the request.") from exc

    async def stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> AsyncIterator[str]:
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json={
                        "model": model or self.settings.ollama_model,
                        "stream": True,
                        "messages": messages,
                        "options": {"temperature": 0.7},
                    },
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        body = json.loads(line)
                        if not isinstance(body, dict):
                            raise OllamaUnavailable("Ollama returned an invalid response chunk.")
                        if body.get("error"):
                            raise OllamaUnavailable("Ollama could not complete the request.")
                        message = body.get("message", {})
                        text = message.get("content", "") if isinstance(message, dict) else ""
                        if text:
                            if not isinstance(text, str):
                                raise OllamaUnavailable("Ollama returned non-text content.")
                            yield text
                        if body.get("done") is True:
                            return
                    raise OllamaUnavailable("Ollama ended the response before completion.")
        except OllamaUnavailable:
            raise
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            logger.exception("Ollama streaming failed")
            raise OllamaUnavailable("Ollama could not complete the request.") from exc

    async def is_available(self, model: str | None = None) -> bool:
        try:
            models = await self.list_models()
        except OllamaUnavailable:
            return False
        return (model or self.settings.ollama_model) in models
