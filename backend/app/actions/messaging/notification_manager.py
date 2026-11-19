from collections import deque


class NotificationManager:
    def __init__(self, maximum_items: int = 100) -> None:
        if maximum_items < 1:
            raise ValueError("maximum_items must be positive.")
        self._items: deque[dict[str, str]] = deque(maxlen=maximum_items)

    def publish(self, event: str, message: str) -> dict[str, str]:
        item = {"event": event, "message": message}
        self._items.append(item)
        return item

    def recent(self) -> list[dict[str, str]]:
        return list(self._items)
