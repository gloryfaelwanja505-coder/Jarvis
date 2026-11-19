class GmailAdapter:
    """Deliberately unavailable until a user-authorized OAuth flow is configured."""

    @property
    def available(self) -> bool:
        return False

    async def send(self, recipient: str, subject: str, body: str) -> None:
        if not recipient.strip() or not subject.strip() or not body.strip():
            raise ValueError("A recipient, subject, and email body are required.")
        raise RuntimeError("Gmail OAuth has not been configured; no email was sent.")
