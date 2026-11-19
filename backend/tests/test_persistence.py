from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.api.routes import chat as chat_routes
from app.main import create_app
from fastapi.testclient import TestClient


def test_conversation_survives_app_restart(client, monkeypatch) -> None:
    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = None
    fake_client.responses.create.return_value = SimpleNamespace(output_text="Persisted reply.")
    monkeypatch.setattr(chat_routes, "create_openai_client", lambda _: fake_client)

    created = client.post("/api/chat", json={"message": "Persist this."}).json()
    conversation_id = created["conversation_id"]
    settings = client.app.state.settings

    restarted_app = create_app(settings.model_copy())
    with TestClient(restarted_app) as restarted_client:
        response = restarted_client.get(f"/api/conversations/{conversation_id}")
        assert response.status_code == 200
        assert [message["content"] for message in response.json()["messages"]] == [
            "Persist this.",
            "Persisted reply.",
        ]


def test_unfinished_chat_task_is_marked_interrupted_after_restart(client, monkeypatch) -> None:
    from app.models import AssistantTask, Message

    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = None
    fake_client.responses.create.return_value = SimpleNamespace(output_text="Saved reply.")
    monkeypatch.setattr(chat_routes, "create_openai_client", lambda _: fake_client)
    completed = client.post("/api/chat", json={"message": "Save a task."}).json()
    conversation_id = completed["conversation_id"]
    with client.app.state.session_factory.begin() as db:
        task = db.query(AssistantTask).filter_by(conversation_id=conversation_id).one()
        assistant_message = db.get(Message, task.assistant_message_id)
        task.assistant_message_id = None
        task.status = "running"
        task.stage = "generating"
        task.completed_at = None
        db.delete(assistant_message)

    restarted_app = create_app(client.app.state.settings.model_copy())
    with TestClient(restarted_app) as restarted_client:
        response = restarted_client.get(f"/api/conversations/{conversation_id}")
        assert response.status_code == 200
        recovered_task = response.json()["tasks"][0]
        assert recovered_task["status"] == "interrupted"
        assert "No action was replayed" in recovered_task["error_message"]
        with restarted_app.state.session_factory() as db:
            recovered = db.query(AssistantTask).filter_by(id=recovered_task["id"]).one()
            assert recovered.stage == "interrupted"


def test_unfinished_call_attempt_is_marked_failed_after_restart(client) -> None:
    from app.models import CallAttempt, CallSession

    call_id = str(uuid4())
    with client.app.state.session_factory.begin() as db:
        db.add(
            CallSession(
                id=call_id,
                status="active",
                started_at=datetime.now(timezone.utc),
            )
        )
        db.add(
            CallAttempt(
                session_id=call_id,
                attempt_number=1,
                channel="webrtc",
                status="in_progress",
            )
        )

    client.app.state.calling_manager.recover_interrupted_sessions()

    with client.app.state.session_factory() as db:
        call = db.get(CallSession, call_id)
        attempt = db.query(CallAttempt).filter_by(session_id=call_id).one()
        assert call.status == "failed"
        assert call.outcome == "backend_restarted"
        assert attempt.status == "failed"
        assert attempt.result == "backend_restarted"
        assert attempt.completed_at is not None
