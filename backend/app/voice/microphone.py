class MicrophonePermissionRequired(RuntimeError):
    pass


class MicrophoneStatus:
    """Reports browser-granted capture status; it never opens a device itself."""

    def __init__(self) -> None:
        self.active = False

    def set_active(self, active: bool) -> None:
        self.active = active

    def snapshot(self) -> dict[str, bool]:
        return {"active": self.active, "capture_is_explicit": True}
