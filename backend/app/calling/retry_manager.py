from collections.abc import Sequence


def planned_attempts(retry_limit: int, channels: Sequence[str]) -> list[tuple[int, str]]:
    if retry_limit < 0:
        raise ValueError("Retry limit cannot be negative.")
    if not channels or any(channel not in {"webrtc", "telephone"} for channel in channels):
        raise ValueError("At least one supported calling channel is required.")
    return [
        (attempt_number, channel)
        for attempt_number, channel in enumerate(
            (channel for _ in range(retry_limit + 1) for channel in channels),
            start=1,
        )
    ]
