import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import monotonic
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.config import Settings
from app.ai.gemini import GeminiError, GeminiProvider

logger = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    def __init__(self, provider: str, message: str) -> None:
        super().__init__(message)
        self.provider = provider


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    requests: int = 0
    estimated_cost: float = 0.0


class AIRouter:
    """Single server-side gateway for OpenAI, DeepSeek, Gemini, and Ollama."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.usage: dict[str, Usage] = {
            name: Usage() for name in ("openai", "deepseek", "gemini", "ollama")
        }
        self.last_provider: str | None = None
        self.gemini = GeminiProvider(settings)

    def _configured(self, provider: str) -> bool:
        if provider == "ollama":
            return bool(self.settings.ollama_base_url.strip() and self.settings.ollama_model.strip())
        if provider == "openai":
            key = self.settings.openai_api_key
        elif provider == "deepseek":
            key = self.settings.deepseek_api_key
        else:
            key = self.settings.gemini_api_key
        return key is not None and bool(key.get_secret_value().strip())

    def _order(self, requested: str | None = None) -> list[str]:
        selected = (requested or self.settings.effective_ai_provider).lower().strip()
        if selected in {"openai", "deepseek", "gemini", "ollama"}:
            order = [selected]
            if self.settings.ai_fallback_enabled:
                order.extend(
                    provider
                    for provider in ("ollama", "openai", "deepseek", "gemini")
                    if provider not in order
                )
            return order
        return ["ollama", "openai", "deepseek", "gemini"]

    def model(self, provider: str) -> str:
        return {
            "openai": self.settings.openai_model,
            "deepseek": self.settings.deepseek_model,
            "gemini": self.settings.gemini_model,
            "ollama": self.settings.ollama_model,
        }[provider]

    async def health(self, provider: str) -> dict[str, object]:
        if not self._configured(provider):
            return {"provider": provider, "configured": False, "available": False, "model": self.model(provider)}
        try:
            if provider == "ollama":
                async with httpx.AsyncClient(timeout=5) as client:
                    response = await client.get(f"{self.settings.ollama_base_url.rstrip('/')}/api/tags")
                    response.raise_for_status()
                    body = response.json()
                models = [item.get("name") for item in body.get("models", []) if isinstance(item, dict)]
                return {"provider": provider, "configured": True, "available": self.model(provider) in models, "model": self.model(provider), "models": models}
            if provider == "openai":
                client = self._openai()
                async with client:
                    await client.models.list()
            elif provider == "deepseek":
                client = self._deepseek()
                async with client:
                    await client.models.list()
            else:
                models = await self.gemini.list_models()
                return {
                    "provider": provider,
                    "state": "configured" if self.model(provider) in models else "model_unavailable",
                    "configured": True,
                    "available": self.model(provider) in models,
                    "model": self.model(provider),
                    "models": models,
                }
            return {"provider": provider, "state": "connected", "configured": True, "available": True, "model": self.model(provider)}
        except Exception as exc:
            logger.info("%s health check failed: %s", provider, type(exc).__name__)
            return {"provider": provider, "configured": True, "available": False, "model": self.model(provider), "error": self._safe_error(provider, exc)}

    def _openai(self) -> AsyncOpenAI:
        if not self.settings.openai_api_key:
            raise ProviderError("openai", "OpenAI credentials are not configured.")
        return AsyncOpenAI(
            api_key=self.settings.openai_api_key.get_secret_value(),
            timeout=self.settings.ai_request_timeout,
            max_retries=0,
        )

    def _deepseek(self) -> AsyncOpenAI:
        if not self.settings.deepseek_api_key:
            raise ProviderError("deepseek", "DeepSeek credentials are not configured.")
        return AsyncOpenAI(
            api_key=self.settings.deepseek_api_key.get_secret_value(),
            base_url=self.settings.deepseek_base_url.rstrip("/"),
            timeout=self.settings.ai_request_timeout,
            max_retries=0,
        )

    async def _deepseek_generate(
        self,
        messages: list[dict[str, str]],
        instruction: str,
        stream: bool,
    ) -> Any:
        client = self._deepseek()
        payload = {
            "model": self.settings.deepseek_model,
            "messages": [{"role": "system", "content": instruction}, *messages],
            "stream": stream,
        }
        if stream:
            return await client.chat.completions.create(**payload)
        async with client:
            return await client.chat.completions.create(**payload)

    async def _openai_generate(self, messages: list[dict[str, str]], instruction: str, stream: bool) -> Any:
        client = self._openai()
        if stream:
            return await client.responses.create(
                model=self.settings.openai_model,
                instructions=instruction,
                input=messages,
                stream=True,
            )
        async with client:
            return await client.responses.create(
                model=self.settings.openai_model,
                instructions=instruction,
                input=messages,
                stream=False,
            )

    async def _gemini_generate(self, messages: list[dict[str, str]], instruction: str, stream: bool) -> Any:
        if stream:
            return self.gemini.stream(messages, instruction)
        text, usage = await self.gemini.generate(messages, instruction)
        return type("GeminiResponse", (), {"text": text, "usage_metadata": usage})()

    async def _ollama_generate(self, messages: list[dict[str, str]], instruction: str, stream: bool) -> Any:
        payload = {
            "model": self.settings.ollama_model,
            "stream": stream,
            "messages": [{"role": "system", "content": instruction}, *messages],
        }
        client = httpx.AsyncClient(timeout=self.settings.ai_request_timeout)
        if stream:
            return client.stream("POST", f"{self.settings.ollama_base_url.rstrip('/')}/api/chat", json=payload)
        try:
            async with client:
                response = await client.post(f"{self.settings.ollama_base_url.rstrip('/')}/api/chat", json=payload)
                response.raise_for_status()
                return response.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            await client.aclose()
            raise ProviderError("ollama", "Ollama could not complete the request.") from exc

    async def generate(self, messages: list[dict[str, str]], instruction: str, provider: str | None = None) -> tuple[str, str]:
        last_error: Exception | None = None
        for candidate in self._order(provider):
            if not self._configured(candidate):
                last_error = ProviderError(candidate, f"{candidate.title()} credentials are not configured.")
                continue
            for attempt in range(2):
                try:
                    async with asyncio.timeout(self.settings.ai_request_timeout):
                        if candidate == "openai":
                            response = await self._openai_generate(messages, instruction, False)
                            content = response.output_text.strip()
                            self._record(candidate, response.usage)
                        elif candidate == "deepseek":
                            response = await self._deepseek_generate(messages, instruction, False)
                            content = response.choices[0].message.content.strip()
                            self._record(candidate, response.usage)
                        elif candidate == "gemini":
                            response = await self._gemini_generate(messages, instruction, False)
                            content = response.text.strip()
                            self._record(candidate, getattr(response, "usage_metadata", None))
                        else:
                            content = (await self._ollama_generate(messages, instruction, False)).strip()
                        if not content:
                            raise ProviderError(candidate, "The provider returned an empty response.")
                        self.last_provider = candidate
                        return content, self.model(candidate)
                except Exception as exc:
                    last_error = exc
                    if attempt == 0 and self._retryable(exc):
                        await asyncio.sleep(0.25)
                        continue
                    logger.warning("%s request failed; fallback=%s", candidate, self.settings.ai_fallback_enabled)
                    break
        raise ProviderError("router", "No configured AI provider could complete the request.") from last_error

    async def stream(self, messages: list[dict[str, str]], instruction: str, provider: str | None = None) -> AsyncIterator[tuple[str, str]]:
        last_error: Exception | None = None
        last_candidate: str | None = None
        for candidate in self._order(provider):
            last_candidate = candidate
            if not self._configured(candidate):
                last_error = ProviderError(candidate, f"{candidate.title()} credentials are not configured.")
                continue
            try:
                async with asyncio.timeout(self.settings.ai_request_timeout):
                    if candidate == "openai":
                        response = await self._openai_generate(messages, instruction, True)
                        async for event in response:
                            if event.type == "response.output_text.delta":
                                self.last_provider = candidate
                                yield event.delta, self.model(candidate)
                    elif candidate == "deepseek":
                        response = await self._deepseek_generate(messages, instruction, True)
                        async for chunk in response:
                            choices = getattr(chunk, "choices", None) or []
                            text = choices[0].delta.content if choices else ""
                            if text:
                                self.last_provider = candidate
                                yield text, self.model(candidate)
                    elif candidate == "gemini":
                        response = await self._gemini_generate(messages, instruction, True)
                        async for chunk in response:
                            if chunk:
                                self.last_provider = candidate
                                yield chunk, self.model(candidate)
                    else:
                        stream = await self._ollama_generate(messages, instruction, True)
                        async with stream as response:
                            response.raise_for_status()
                            async for line in response.aiter_lines():
                                if line:
                                    body = __import__("json").loads(line)
                                    text = body.get("message", {}).get("content", "")
                                    if text:
                                        self.last_provider = candidate
                                        yield text, self.model(candidate)
                return
            except Exception as exc:
                last_error = exc
                logger.warning("%s stream failed", candidate, exc_info=True)
                if not self.settings.ai_fallback_enabled:
                    break
        if isinstance(last_error, ProviderError):
            raise last_error
        raise ProviderError("router", self._stream_error(last_error, last_candidate))

    def _stream_error(self, exc: Exception | None, provider: str | None) -> str:
        if exc is None:
            return "No configured AI provider could stream a response."
        status = getattr(exc, "status_code", None)
        if status == 402:
            if provider == "deepseek":
                return "DeepSeek rejected the request because its account balance is insufficient."
            return f"{provider.title() if provider else 'The AI provider'} has insufficient account balance."
        if status in {401, 403}:
            return "The selected AI provider rejected the API credentials."
        if status == 429:
            return "The selected AI provider is rate-limited or out of quota."
        if isinstance(exc, TimeoutError):
            return "The selected AI provider timed out."
        return "No configured AI provider could stream a response."

    def _retryable(self, exc: Exception) -> bool:
        return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, TimeoutError))

    def _record(self, provider: str, usage: Any) -> None:
        item = self.usage[provider]
        item.requests += 1
        if usage is not None:
            item.prompt_tokens += int(getattr(usage, "input_tokens", getattr(usage, "prompt_token_count", 0)) or 0)
            item.completion_tokens += int(getattr(usage, "output_tokens", getattr(usage, "candidates_token_count", 0)) or 0)
            pricing = {
                "gpt-4.1-mini": (0.40, 1.60),
                "gemini-2.5-flash": (0.30, 2.50),
            }
            if self.settings.ai_pricing_json:
                try:
                    pricing.update(json.loads(self.settings.ai_pricing_json))
                except (TypeError, ValueError, json.JSONDecodeError):
                    logger.warning("Ignoring invalid AI_PRICING_JSON.")
            prompt_rate, completion_rate = pricing.get(self.model(provider), (0.0, 0.0))
            item.estimated_cost += (
                item.prompt_tokens * prompt_rate + item.completion_tokens * completion_rate
            ) / 1_000_000

    def _safe_error(self, provider: str, exc: Exception) -> str:
        if isinstance(exc, ProviderError):
            return str(exc)
        return f"{provider.title()} is unavailable. Check its configuration and network connection."

    async def status(self) -> dict[str, object]:
        providers = [
            await self.health(provider)
            for provider in ("openai", "deepseek", "gemini", "ollama")
        ]
        return {
            "providers": providers,
            "default_provider": self.settings.effective_ai_provider,
            "fallback_enabled": self.settings.ai_fallback_enabled,
            "usage": {name: vars(value) for name, value in self.usage.items()},
            "last_provider": self.last_provider,
            "monthly_spending_limit": self.settings.monthly_spending_limit,
        }
