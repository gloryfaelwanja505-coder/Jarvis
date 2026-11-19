class WhatsAppAdapter:
    @property
    def available(self) -> bool:
        return False

    async def send(self, recipient: str, body: str) -> None:
        if not recipient.strip() or not body.strip():
            raise ValueError("A recipient and message body are required.")
        raise RuntimeError("No authorized WhatsApp Business or companion adapter is configured.")
