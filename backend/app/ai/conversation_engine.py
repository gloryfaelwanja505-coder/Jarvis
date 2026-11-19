from collections.abc import AsyncIterator

from app.ai.ai_manager import AIManager


class ConversationEngine:
    def __init__(self, manager: AIManager) -> None:
        self.manager = manager

    async def respond(
        self,
        messages: list[tuple[str, str]],
        preferences: list[tuple[str, str]] | None = None,
    ) -> str:
        return await self.manager.generate(messages, preferences or [])

    async def stream(
        self,
        messages: list[tuple[str, str]],
        preferences: list[tuple[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        async for part in self.manager.stream(messages, preferences or []):
            yield part
