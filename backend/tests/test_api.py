import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from openai import OpenAIError

from app.api.routes import chat as chat_routes


def mock_client(response_text: str = "At your service.") -> AsyncMock:
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    client.responses.create.return_value = SimpleNamespace(output_text=response_text)
    return client


def test_health_does_not_expose_credentials(client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "jarvis",
        "ai_configured": True,
        "ai_available": True,
        "ai_provider": "openai",
        "model": "gpt-4.1-mini",
        "calling_auth_configured": True,
        "scheduler_running": True,
    }


def test_system_metrics_returns_live_cpu_and_memory_values(client) -> None:
    response = client.get("/api/system/metrics")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"cpu_percent", "memory_percent", "memory_used", "memory_total"}
    assert 0 <= body["cpu_percent"] <= 100
    assert 0 <= body["memory_percent"] <= 100
    assert 0 < body["memory_used"] <= body["memory_total"]


def test_voice_status_reports_configured_wake_phrase(client) -> None:
    response = client.get("/api/voice/status")

    assert response.status_code == 200
    assert response.json()["wake_word_phrase"] == "Hello JARVIS Scott here"
    assert response.json()["wake_word_listening"] is False


def test_wake_word_websocket_uses_local_detector(client) -> None:
    class FakeWakeWord:
        available = True
        phrase = "Hello JARVIS Scott here"

        def detect(self, pcm: bytes) -> bool:
            return pcm == b"\x01\x00"

    client.app.state.audio_manager.wake_word = FakeWakeWord()
    with client.websocket_connect("/api/voice/wake-word") as websocket:
        websocket.send_bytes(b"\x01\x00")
        assert websocket.receive_json() == {"detected": True}
        assert client.get("/api/voice/status").json()["wake_word_listening"] is True

    assert client.get("/api/voice/status").json()["wake_word_listening"] is False


def test_chat_saves_user_and_assistant_messages(client, monkeypatch) -> None:
    fake_client = mock_client()
    monkeypatch.setattr(chat_routes, "create_openai_client", lambda _: fake_client)

    response = client.post("/api/chat", json={"message": "Hello, JARVIS."})

    assert response.status_code == 200
    body = response.json()
    assert body["message"]["content"] == "At your service."
    assert body["message"]["role"] == "assistant"
    conversation = client.get(f"/api/conversations/{body['conversation_id']}")
    assert conversation.status_code == 200
    assert [message["role"] for message in conversation.json()["messages"]] == [
        "user",
        "assistant",
    ]
    assert conversation.json()["tasks"][0]["status"] == "completed"
    assert conversation.json()["tasks"][0]["stage"] == "completed"
    assert fake_client.responses.create.await_args.kwargs["model"] == "gpt-4.1-mini"


def test_chat_uses_configured_ollama_model(client, monkeypatch) -> None:
    settings = client.app.state.settings.model_copy(
        update={
            "ai_provider": "ollama",
            "ollama_model": "llama3.2:1b",
            "openai_api_key": None,
        }
    )
    client.app.state.settings = settings
    class FakeManager:
        personality = "test personality"

        async def generate(self, messages, preferences):
            assert messages == [("user", "Keep this local.")]
            assert preferences == []
            return "A local reply."

    client.app.state.ai_manager = FakeManager()
    response = client.post("/api/chat", json={"message": "Keep this local."})

    assert response.status_code == 200
    assert response.json()["message"]["content"] == "A local reply."
    assert response.json()["model"] == "llama3.2:1b"


def test_streaming_chat_uses_ollama_deltas(client, monkeypatch) -> None:
    client.app.state.settings = client.app.state.settings.model_copy(
        update={"ai_provider": "ollama", "ollama_model": "llama3.2:1b"}
    )

    class FakeManager:
        personality = "test personality"

        async def stream(self, _messages, _preferences):
            yield "Local "
            yield "reply."

    client.app.state.ai_manager = FakeManager()
    response = client.post("/api/chat/stream", json={"message": "Keep this local."})

    assert response.status_code == 200
    assert "Local " in response.text
    assert "reply." in response.text
    assert "event: done" in response.text
    assert '"model": "llama3.2:1b"' in response.text


def test_chat_continues_existing_conversation(client, monkeypatch) -> None:
    fake_client = mock_client("I remember our conversation.")
    monkeypatch.setattr(chat_routes, "create_openai_client", lambda _: fake_client)
    first = client.post("/api/chat", json={"message": "Remember this context."}).json()

    response = client.post(
        "/api/chat",
        json={
            "message": "What did I say?",
            "conversation_id": first["conversation_id"],
        },
    )

    assert response.status_code == 200
    prompt = fake_client.responses.create.await_args.kwargs["input"]
    assert [item["role"] for item in prompt] == ["user", "assistant", "user"]


def test_chat_validates_input(client) -> None:
    assert client.post("/api/chat", json={"message": "  "}).status_code == 422
    assert client.post("/api/chat", json={"message": "x" * 8001}).status_code == 422


def test_chat_requires_api_key_without_saving_message(client) -> None:
    client.app.state.settings = client.app.state.settings.model_copy(
        update={"openai_api_key": None}
    )

    response = client.post("/api/chat", json={"message": "Hello"})

    assert response.status_code == 503
    assert client.get("/api/conversations").json() == []


def test_chat_reports_openai_errors(client, monkeypatch) -> None:
    fake_client = mock_client()
    fake_client.responses.create.side_effect = OpenAIError("upstream unavailable")
    monkeypatch.setattr(chat_routes, "create_openai_client", lambda _: fake_client)

    response = client.post("/api/chat", json={"message": "Hello"})

    assert response.status_code == 502
    assert response.json()["detail"] == "The AI service could not complete the request."


def test_streaming_chat_saves_complete_response(client, monkeypatch) -> None:
    async def deltas():
        yield SimpleNamespace(type="response.output_text.delta", delta="Streamed ")
        yield SimpleNamespace(type="response.output_text.delta", delta="reply.")

    fake_client = mock_client()
    fake_client.responses.create.return_value = deltas()
    monkeypatch.setattr(chat_routes, "create_openai_client", lambda _: fake_client)

    response = client.post("/api/chat/stream", json={"message": "Stream this."})

    assert response.status_code == 200
    assert "event: delta" in response.text
    assert "Streamed " in response.text
    assert "event: done" in response.text
    conversation_id = response.text.split('"conversation_id": "')[1].split('"')[0]
    conversation = client.get(f"/api/conversations/{conversation_id}").json()
    assert conversation["messages"][-1]["content"] == "Streamed reply."


def test_streaming_chat_retry_uses_the_saved_task_without_duplicate_messages(client, monkeypatch) -> None:
    async def deltas():
        yield SimpleNamespace(type="response.output_text.delta", delta="Recovered reply.")

    fake_client = mock_client()
    fake_client.responses.create.side_effect = [
        OpenAIError("temporary outage"),
        deltas(),
    ]
    monkeypatch.setattr(chat_routes, "create_openai_client", lambda _: fake_client)
    task_id = str(uuid4())

    first = client.post(
        "/api/chat/stream",
        json={"message": "Keep this request.", "task_id": task_id},
    )
    meta = next(
        json.loads(line.removeprefix("data: "))
        for line in first.text.splitlines()
        if line.startswith("data: ") and "task_id" in line
    )
    conversation_id = meta["conversation_id"]
    failed_conversation = client.get(f"/api/conversations/{conversation_id}").json()
    assert failed_conversation["tasks"][0]["status"] == "failed"
    assert [message["role"] for message in failed_conversation["messages"]] == ["user"]

    payload = {
        "message": "Keep this request.",
        "conversation_id": conversation_id,
        "task_id": task_id,
    }
    retried = client.post("/api/chat/stream", json=payload)
    assert "Recovered reply." in retried.text
    assert "event: done" in retried.text

    duplicate = client.post("/api/chat/stream", json=payload)
    assert "Recovered reply." in duplicate.text
    conversation = client.get(f"/api/conversations/{conversation_id}").json()
    assert [message["role"] for message in conversation["messages"]] == ["user", "assistant"]
    assert conversation["tasks"][0]["status"] == "completed"
    assert conversation["tasks"][0]["attempt_count"] == 2
    assert fake_client.responses.create.await_count == 2


def test_chat_task_id_cannot_be_reused_for_another_message(client, monkeypatch) -> None:
    fake_client = mock_client()
    monkeypatch.setattr(chat_routes, "create_openai_client", lambda _: fake_client)
    task_id = str(uuid4())
    first = client.post("/api/chat", json={"message": "Original message.", "task_id": task_id})
    assert first.status_code == 200

    duplicate = client.post(
        "/api/chat",
        json={"message": "Different message.", "task_id": task_id},
    )
    assert duplicate.status_code == 409
    assert fake_client.responses.create.await_count == 1


def test_chat_timeout_is_recorded_and_reported(client, monkeypatch) -> None:
    import asyncio

    async def delayed_response(**_kwargs):
        await asyncio.sleep(0.05)

    fake_client = mock_client()
    fake_client.responses.create.side_effect = delayed_response
    monkeypatch.setattr(chat_routes, "create_openai_client", lambda _: fake_client)
    monkeypatch.setattr(chat_routes, "CHAT_TIMEOUT_SECONDS", 0.001)
    task_id = str(uuid4())

    response = client.post(
        "/api/chat",
        json={"message": "This will time out.", "task_id": task_id},
    )

    assert response.status_code == 504
    conversation = client.get("/api/conversations").json()[0]
    recovered = client.get(f"/api/conversations/{conversation['id']}").json()
    assert recovered["tasks"][0]["status"] == "failed"
    assert recovered["tasks"][0]["attempt_count"] == 1


def test_calling_schedules_require_authentication_and_are_editable(client) -> None:
    headers = {"X-Calling-Token": "test-calling-token-that-is-at-least-32-chars"}

    assert client.get("/api/calling/schedules").status_code == 401
    schedules = client.get("/api/calling/schedules", headers=headers)
    assert schedules.status_code == 200
    assert [(item["id"], item["local_time"][:5]) for item in schedules.json()] == [
        ("evening", "17:00"),
        ("morning", "07:00"),
    ]

    updated = client.put(
        "/api/calling/schedules/morning",
        headers=headers,
        json={"local_time": "07:15:00", "enabled": False},
    )
    assert updated.status_code == 200
    assert updated.json()["local_time"].startswith("07:15")
    assert updated.json()["enabled"] is False


def test_calling_cors_allows_authenticated_schedule_updates(client) -> None:
    response = client.options(
        "/api/calling/schedules/morning",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type,x-calling-token",
        },
    )

    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_calling_api_requires_https_when_enabled(client) -> None:
    client.app.state.settings = client.app.state.settings.model_copy(
        update={"require_https": True}
    )

    response = client.get(
        "/api/calling/schedules",
        headers={"X-Calling-Token": "test-calling-token-that-is-at-least-32-chars"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Calling API access requires HTTPS."


def test_calling_preferences_require_explicit_telephone_consent(client) -> None:
    headers = {"X-Calling-Token": "test-calling-token-that-is-at-least-32-chars"}
    response = client.put(
        "/api/calling/preferences",
        headers=headers,
        json={
            "enabled": True,
            "do_not_disturb": False,
            "timezone": "Africa/Nairobi",
            "retry_limit": 1,
            "retry_delay_seconds": 300,
            "telephone_fallback_enabled": True,
            "telephone_billing_confirmed": False,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Telephone fallback requires explicit billing confirmation."


def test_calling_status_does_not_expose_secrets(client) -> None:
    status_response = client.get("/api/calling/status")

    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["test_mode"] is True
    assert status_data["telephone_live_calls_enabled"] is False
    assert "test-calling-token" not in status_response.text
