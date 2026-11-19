from collections.abc import AsyncIterator

from app.ai.ollama_client import OllamaClient
from app.ai.personality import DEFAULT_PERSONALITY, system_prompt
from app.ai.provider_manager import ProviderManager
from app.config import Settings
from app.ai.router import AIRouter, ProviderError


class AIManager:
    def __init__(
        self,
        settings: Settings,
        ollama: OllamaClient | None = None,
    ) -> None:
        self.settings = settings
        self.ollama = ollama or OllamaClient(settings)
        self.providers = ProviderManager(settings, self.ollama)
        self.personality = DEFAULT_PERSONALITY
        self.router = AIRouter(settings)

    def _messages(
        self,
        history: list[tuple[str, str]],
        preferences: list[tuple[str, str]],
    ) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": system_prompt(self.personality, preferences)},
            *[{"role": role, "content": content} for role, content in history],
        ]

    async def generate(
        self,
        history: list[tuple[str, str]],
        preferences: list[tuple[str, str]] | None = None,
    ) -> str:
        if self.settings.effective_ai_provider == "ollama" and self.settings.default_ai_provider is None:
            return await self.ollama.generate(self._messages(history, preferences or []))
        content, _ = await self.router.generate(
            self._messages(history, preferences or [])[1:],
            system_prompt(self.personality, preferences or []),
            self.settings.effective_ai_provider,
        )
        return content

    async def stream(
        self,
        history: list[tuple[str, str]],
        preferences: list[tuple[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        if self.settings.effective_ai_provider == "ollama" and self.settings.default_ai_provider is None:
            async for text in self.ollama.stream(self._messages(history, preferences or [])):
                yield text
            return
        async for text, _ in self.router.stream(
            self._messages(history, preferences or [])[1:],
            system_prompt(self.personality, preferences or []),
            self.settings.effective_ai_provider,
        ):
            yield text
