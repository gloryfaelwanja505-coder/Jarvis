import asyncio
from collections.abc import Awaitable, Callable


class SpeechQueue:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._current: asyncio.Task[None] | None = None

    async def play(self, speak: Callable[[], Awaitable[None]]) -> None:
        async with self._lock:
            self._current = asyncio.current_task()
            try:
                await speak()
            finally:
                self._current = None

    async def interrupt(self) -> bool:
        task = self._current
        if task is None or task is asyncio.current_task():
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return True
        return False
