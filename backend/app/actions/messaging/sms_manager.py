class SmsManager:
    def send(self, recipient: str, body: str) -> None:
        if not recipient.strip() or not body.strip():
            raise ValueError("A recipient and message body are required.")
        raise RuntimeError("SMS delivery is unavailable; configure a supported phone bridge.")
