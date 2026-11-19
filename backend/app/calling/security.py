import hmac
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, WebSocket, status

from app.config import Settings


class CallingRateLimiter:
    def __init__(self, limit: int = 60, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, identity: str) -> bool:
        now = time.monotonic()
        with self._lock:
            requests = self._requests[identity]
            while requests and now - requests[0] >= self.window_seconds:
                requests.popleft()
            if len(requests) >= self.limit:
                return False
            requests.append(now)
            return True


def _provided_token_matches(settings: Settings, token: str | None) -> bool:
    if not settings.calling_auth_configured or not token:
        return False
    expected = settings.calling_access_token.get_secret_value()
    return hmac.compare_digest(expected, token)


def require_calling_access(request: Request) -> str:
    settings: Settings = request.app.state.settings
    if settings.require_https and request.url.scheme != "https":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Calling API access requires HTTPS.",
        )
    if not settings.calling_auth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Calling access is disabled. Configure JARVIS_CALLING_ACCESS_TOKEN (at least 32 characters).",
        )
    peer = request.client.host if request.client else "unknown"
    if not request.app.state.calling_rate_limiter.allow(peer):
        raise HTTPException(status_code=429, detail="Calling API rate limit exceeded.")
    token = request.headers.get("X-Calling-Token")
    if not _provided_token_matches(settings, token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid calling access token.")
    return token


def websocket_token_matches(websocket: WebSocket) -> bool:
    settings: Settings = websocket.app.state.settings
    if settings.require_https and websocket.url.scheme != "wss":
        return False
    offered = websocket.headers.get("sec-websocket-protocol", "")
    protocols = {item.strip() for item in offered.split(",")}
    auth_protocols = [item.removeprefix("jarvis-token.") for item in protocols if item.startswith("jarvis-token.")]
    return len(auth_protocols) == 1 and _provided_token_matches(settings, auth_protocols[0])
