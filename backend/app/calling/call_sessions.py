import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

logger = logging.getLogger(__name__)


class CallConnectionHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._call_events: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    @property
    def connected_clients(self) -> int:
        return len(self._clients)

    async def connect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.add(websocket)
        await websocket.send_json({"type": "connected", "client_count": self.connected_clients})

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)

    def create_call_queue(self, call_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._call_events[call_id] = queue
        return queue

    def discard_call_queue(self, call_id: str) -> None:
        self._call_events.pop(call_id, None)

    async def publish(self, event: dict[str, Any], call_id: str | None = None) -> None:
        async with self._lock:
            clients = tuple(self._clients)
        failed: list[WebSocket] = []
        for websocket in clients:
            try:
                await websocket.send_json(event)
            except (WebSocketDisconnect, RuntimeError):
                failed.append(websocket)
                logger.info("Removing disconnected calling websocket")
        if failed:
            async with self._lock:
                self._clients.difference_update(failed)

    async def signal(self, message: dict[str, Any]) -> None:
        call_id = str(message.get("call_id", ""))
        queue = self._call_events.get(call_id)
        if queue is not None and message.get("type") in {"answer", "decline", "end"}:
            await queue.put(message)
        if message.get("type") in {"offer", "answer_sdp", "ice_candidate"}:
            response = message.get("response")
            if not isinstance(response, dict):
                response = {"type": message["type"], "call_id": call_id, "payload": message.get("payload", {})}
            await self.publish(response, call_id=call_id)

    async def close(self) -> None:
        async with self._lock:
            clients = tuple(self._clients)
            self._clients.clear()
        for websocket in clients:
            try:
                await websocket.close(code=1001)
            except (WebSocketDisconnect, RuntimeError):
                logger.debug("Calling websocket already closed")


def decode_signal(message: str) -> dict[str, Any]:
    try:
        parsed = json.loads(message)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid signaling message.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Signaling message must be a JSON object.")
    return parsed
