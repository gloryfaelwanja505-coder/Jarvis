import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class GeminiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class GeminiStatus:
    state: str
    configured: bool
    available: bool
    model: str
    models: list[str]
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": "gemini",
            "state": self.state,
            "configured": self.configured,
            "available": self.available,
            "model": self.model,
            "models": self.models,
            **({"error": self.error} if self.error else {}),
        }


class GeminiProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _client(self) -> Any:
        if self.settings.gemini_api_key is None or not self.settings.gemini_api_key.get_secret_value().strip():
            raise GeminiError("Gemini API key is not configured.")
        try:
            from google import genai
        except ImportError as exc:
            raise GeminiError("The official google-genai package is not installed.") from exc
        from google.genai import types

        return genai.Client(
            api_key=self.settings.gemini_api_key.get_secret_value(),
            http_options=types.HttpOptions(timeout=int(self.settings.ai_request_timeout * 1000)),
        )

    @staticmethod
    def _model_name(name: str) -> str:
        return name.removeprefix("models/")

    def _diagnostic(self, exc: Exception) -> GeminiError:
        status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if status in {401, 403}:
            return GeminiError("Gemini authentication or project permission failed (401/403). Check the API key restrictions and Generative Language API access.", int(status))
        if status == 404:
            return GeminiError(f"Gemini model or endpoint was not found (404): {self.settings.gemini_model}.", 404)
        if status == 429:
            return GeminiError("Gemini quota or rate limit exceeded (429).", 429)
        if status in {400}:
            return GeminiError(f"Gemini rejected the request (400): {type(exc).__name__}.", 400)
        if status in {500, 503}:
            return GeminiError(f"Gemini service is unavailable ({status}).", int(status))
        if isinstance(exc, (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException)) or "timeout" in type(exc).__name__.lower():
            return GeminiError("Gemini request timed out.")
        if isinstance(exc, httpx.NetworkError):
            return GeminiError("Gemini network connection failed.")
        return GeminiError("Gemini request failed. Check network access and API configuration.")

    async def list_models(self) -> list[str]:
        try:
            client = self._client()
            pager = await asyncio.to_thread(client.models.list)
            models: list[str] = []
            for model in pager:
                supported = getattr(model, "supported_actions", None) or getattr(model, "supported_generation_methods", None) or []
                if not supported or "generateContent" in supported or "generate_content" in supported:
                    name = getattr(model, "name", None)
                    if isinstance(name, str):
                        models.append(self._model_name(name))
            return sorted(set(models))
        except GeminiError:
            raise
        except Exception as exc:
            raise self._diagnostic(exc) from exc

    async def generate(self, messages: Sequence[dict[str, str]], instruction: str) -> tuple[str, Any]:
        try:
            client = self._client()
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=self.settings.gemini_model,
                    contents=[
                        {
                            "role": "model" if item["role"] == "assistant" else "user",
                            "parts": [{"text": item["content"]}],
                        }
                        for item in messages
                    ],
                    config={"system_instruction": instruction},
                ),
                timeout=self.settings.ai_request_timeout,
            )
            text = (response.text or "").strip()
            if not text:
                raise GeminiError("Gemini returned an empty response.")
            return text, getattr(response, "usage_metadata", None)
        except GeminiError:
            raise
        except Exception as exc:
            raise self._diagnostic(exc) from exc

    async def stream(self, messages: Sequence[dict[str, str]], instruction: str) -> AsyncIterator[str]:
        try:
            client = self._client()
            stream = await asyncio.to_thread(
                client.models.generate_content_stream,
                model=self.settings.gemini_model,
                contents=[
                    {
                        "role": "model" if item["role"] == "assistant" else "user",
                        "parts": [{"text": item["content"]}],
                    }
                    for item in messages
                ],
                config={"system_instruction": instruction},
            )
            for response in stream:
                text = response.text or ""
                if text:
                    yield text
        except GeminiError:
            raise
        except Exception as exc:
            raise self._diagnostic(exc) from exc

    async def test_connection(self) -> dict[str, object]:
        if self.settings.gemini_api_key is None or not self.settings.gemini_api_key.get_secret_value().strip():
            return GeminiStatus("not_configured", False, False, self.settings.gemini_model, [], "Gemini API key is not configured.").as_dict()
        try:
            models = await self.list_models()
            if self.settings.gemini_model not in models:
                return GeminiStatus("model_unavailable", True, False, self.settings.gemini_model, models, f"Configured model is not available: {self.settings.gemini_model}.").as_dict()
            text = ""
            last_error: GeminiError | None = None
            for attempt in range(3):
                try:
                    text, _ = await self.generate(
                        [{"role": "user", "content": "Hello JARVIS. Confirm your identity and report that Gemini is operational."}],
                        "You are JARVIS. Answer the verification request directly.",
                    )
                    break
                except GeminiError as exc:
                    last_error = exc
                    if exc.status not in {429, 500, 503} or attempt == 2:
                        raise
                    await asyncio.sleep(0.5 * (2**attempt))
            if last_error is not None and not text:
                raise last_error
            return GeminiStatus("connected", True, bool(text), self.settings.gemini_model, models).as_dict()
        except GeminiError as exc:
            state = (
                "authentication_failed"
                if exc.status in {401, 403}
                else "quota_exceeded"
                if exc.status == 429
                else "service_unavailable"
                if exc.status in {500, 503}
                else "timeout"
                if "timed out" in str(exc).lower()
                else "error"
            )
            return GeminiStatus(state, True, False, self.settings.gemini_model, locals().get("models", []), str(exc)).as_dict()
