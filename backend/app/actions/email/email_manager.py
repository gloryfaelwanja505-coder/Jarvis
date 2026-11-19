class EmailManager:
    def __init__(self, drafts) -> None:
        self.drafts = drafts

    def create_draft(self, db, recipient: str, subject: str, body: str):
        return self.drafts.create(db, recipient, subject, body)

    def send(self, recipient: str, subject: str, body: str) -> None:
        if not recipient.strip() or not subject.strip() or not body.strip():
            raise ValueError("A recipient, subject, and email body are required.")
        raise RuntimeError("Email delivery is unavailable until an authorized adapter is configured.")
