from app.models import AssistantAction, AssistantActionAudit


def test_approved_preference_is_persisted_and_used_as_chat_context(client) -> None:
    saved = client.post(
        "/api/memory",
        json={"key": "tea", "value": "prefers peppermint tea", "approved": True},
    )
    assert saved.status_code == 201

    assert client.get("/api/memory").json()[0]["value"] == "prefers peppermint tea"
    with client.app.state.session_factory() as db:
        memories = client.app.state.ai_context.approved_preferences(db)
    assert memories == [("tea", "prefers peppermint tea")]
    assert client.delete(f"/api/memory/{saved.json()['id']}").status_code == 204
    assert client.get("/api/memory").json() == []


def test_memory_rejects_unapproved_preference(client) -> None:
    response = client.post(
        "/api/memory",
        json={"key": "address", "value": "private", "approved": False},
    )
    assert response.status_code == 400
    assert client.get("/api/memory").json() == []


def test_email_draft_approval_is_audited_but_never_sends(client) -> None:
    draft = client.post(
        "/api/actions/drafts",
        json={
            "action_type": "email",
            "recipient": "friend@example.com",
            "subject": "Hello",
            "body": "A locally saved draft.",
        },
    )
    assert draft.status_code == 201
    assert draft.json()["status"] == "draft"

    approved = client.post(f"/api/actions/{draft.json()['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved_not_sent"

    with client.app.state.session_factory() as db:
        action = db.get(AssistantAction, draft.json()["id"])
        audit = db.query(AssistantActionAudit).filter_by(action_id=action.id).all()
        assert action.status == "approved_not_sent"
        assert [event.event for event in audit] == ["draft_created", "approved_not_sent"]
        assert "no message was sent" in audit[0].detail.lower()


def test_action_draft_validates_email_address(client) -> None:
    response = client.post(
        "/api/actions/drafts",
        json={
            "action_type": "email",
            "recipient": "not-an-email",
            "subject": "Hello",
            "body": "Draft only.",
        },
    )
    assert response.status_code == 422


def test_ollama_model_list_and_selection_are_persisted(client) -> None:
    client.app.state.settings.ai_provider = "ollama"

    class FakeProviders:
        async def local_models(self):
            return ["llama3.2:1b", "qwen2.5:1.5b"]

        async def select_local_model(self, model):
            if model not in await self.local_models():
                from app.ai.ollama_client import OllamaUnavailable

                raise OllamaUnavailable("That model is not installed in Ollama.")
            client.app.state.settings.ollama_model = model
            return model

    client.app.state.ai_manager.providers = FakeProviders()
    status = client.get("/api/ai/status")
    assert status.status_code == 200
    assert status.json()["models"] == ["llama3.2:1b", "qwen2.5:1.5b"]

    selected = client.put("/api/ai/model", json={"model": "qwen2.5:1.5b"})
    assert selected.status_code == 200
    assert selected.json()["model"] == "qwen2.5:1.5b"


def test_voice_status_reports_disabled_hardware_features_without_failing_startup(client) -> None:
    response = client.get("/api/voice/status")
    assert response.status_code == 200
    assert response.json()["capture_requires_user_activation"] is True
    assert response.json()["wake_word_listening"] is False
    assert response.json()["microphone_active"] is False


def test_voice_transcription_is_unavailable_without_local_model(client) -> None:
    response = client.post(
        "/api/voice/transcribe?sample_rate=16000",
        content=b"\x00\x00" * 8000,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 503
