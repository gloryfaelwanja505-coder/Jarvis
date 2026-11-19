import asyncio
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from starlette.websockets import WebSocketDisconnect
from pydantic import SecretStr

from app.calling.conversation_engine import ConversationEngine
from app.calling.providers.telephone import (
    TelephoneUnavailable,
    TwilioTelephoneProvider,
    decode_mulaw,
    encode_mulaw,
)
from app.calling.schemas import CallControlMessage
from app.config import Settings
from app.models import CallSession
from app.models.conversation import utc_now


ACCESS_TOKEN = "test-calling-token-that-is-at-least-32-chars"


def insert_call(client, status: str = "queued") -> str:
    call_id = str(uuid4())
    with client.app.state.session_factory() as db:
        db.add(CallSession(id=call_id, status=status, started_at=utc_now() if status == "active" else None))
        db.commit()
    return call_id


def test_calling_websocket_authenticates_subprotocol_token(client) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/api/calling/ws",
            subprotocols=["jarvis.v1", "jarvis-token.invalid"],
        ):
            pass

    with client.websocket_connect(
        "/api/calling/ws",
        subprotocols=["jarvis.v1", f"jarvis-token.{ACCESS_TOKEN}"],
    ) as websocket:
        assert websocket.receive_json()["type"] == "connected"
        websocket.send_text("not-json")
        assert websocket.receive_json()["type"] == "error"


def test_answer_decline_and_end_update_call_sessions(client) -> None:
    manager = client.app.state.calling_manager
    answer_id = insert_call(client)
    manager.hub.create_call_queue(answer_id)
    answered = asyncio.run(
        manager.control_call(CallControlMessage(type="answer", call_id=answer_id).model_dump())
    )
    assert answered["status"] == "connecting"
    assert manager.hub._call_events[answer_id].get_nowait()["type"] == "answer"
    repeated_answer = asyncio.run(
        manager.control_call(CallControlMessage(type="answer", call_id=answer_id).model_dump())
    )
    assert repeated_answer["status"] == "connecting"
    assert manager.hub._call_events[answer_id].empty()
    ended_answer = asyncio.run(
        manager.control_call(
            CallControlMessage(type="end", call_id=answer_id).model_dump()
        )
    )
    assert ended_answer["status"] == "cancelled"

    decline_id = insert_call(client)
    declined = asyncio.run(
        manager.control_call(CallControlMessage(type="decline", call_id=decline_id).model_dump())
    )
    assert declined["status"] == "declined"

    end_id = insert_call(client, "active")
    ended = asyncio.run(
        manager.control_call(CallControlMessage(type="end", call_id=end_id).model_dump())
    )
    assert ended["status"] == "completed"
    with client.app.state.session_factory() as db:
        assert db.get(CallSession, end_id).ended_at is not None


def test_webrtc_disconnect_marks_active_call_failed(client) -> None:
    call_id = insert_call(client, "active")

    asyncio.run(client.app.state.calling_manager.mark_disconnected(call_id))

    with client.app.state.session_factory() as db:
        session = db.get(CallSession, call_id)
        assert session.status == "failed"
        assert session.ended_at is not None
        assert session.outcome == "webrtc_connection_lost"


def test_signaling_input_rejects_malformed_candidates() -> None:
    with pytest.raises(ValueError):
        CallControlMessage(
            type="ice_candidate",
            call_id=str(uuid4()),
            payload={"candidate": "not-an-ice-candidate"},
        )


def test_answer_offer_and_ice_are_forwarded_to_webrtc_provider(client, monkeypatch) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    manager = client.app.state.calling_manager
    call_id = insert_call(client)
    provider = SimpleNamespace(
        accept_offer=AsyncMock(return_value="v=0\r\ns=JARVIS\r\n"),
        add_ice_candidate=AsyncMock(),
        close=AsyncMock(),
    )
    monkeypatch.setattr(manager.router, "webrtc", provider)

    answered = asyncio.run(
        manager.control_call(CallControlMessage(type="answer", call_id=call_id).model_dump())
    )
    offer = asyncio.run(
        manager.control_call(
            CallControlMessage(
                type="offer",
                call_id=call_id,
                payload={"sdp": "v=0\r\ns=browser\r\n"},
            ).model_dump()
        )
    )
    candidate = {
        "candidate": "candidate:1 1 UDP 1 127.0.0.1 9999 typ host",
        "sdpMid": "0",
        "sdpMLineIndex": 0,
    }
    acknowledged = asyncio.run(
        manager.control_call(
            CallControlMessage(
                type="ice_candidate",
                call_id=call_id,
                payload=candidate,
            ).model_dump()
        )
    )

    assert answered["status"] == "connecting"
    assert offer["payload"]["sdp"].startswith("v=0")
    assert acknowledged["type"] == "signal_ack"
    provider.accept_offer.assert_awaited_once()
    provider.add_ice_candidate.assert_awaited_once_with(call_id, candidate)


def test_test_mode_never_attempts_paid_telephone_call(client) -> None:
    settings = client.app.state.settings
    telephone = TwilioTelephoneProvider(
        settings.model_copy(
            update={
                "telephone_provider": "twilio",
                "test_mode": True,
                "twilio_account_sid": SecretStr("AC000"),
                "twilio_auth_token": SecretStr("test-auth"),
                "twilio_from_number": SecretStr("+15005550006"),
                "twilio_to_number": SecretStr("+15005550006"),
                "twilio_public_base_url": "https://calls.example.test",
            }
        )
    )
    assert telephone.configured is True
    with pytest.raises(TelephoneUnavailable, match="Test mode"):
        asyncio.run(telephone.place_call(CallSession(id=str(uuid4()), status="queued")))


def test_twilio_webhook_signature_is_verified() -> None:
    settings = Settings(
        _env_file=None,
        telephone_provider="twilio",
        twilio_account_sid=SecretStr("AC000"),
        twilio_auth_token=SecretStr("test-auth"),
        twilio_from_number=SecretStr("+15005550006"),
        twilio_to_number=SecretStr("+15005550006"),
        twilio_public_base_url="https://calls.example.test",
    )
    provider = TwilioTelephoneProvider(settings)
    url = "https://calls.example.test/api/calling/webhooks/twilio/status?call_id=abc"
    values = {"CallSid": "CA123", "CallStatus": "completed"}
    canonical = url + "".join(key + values[key] for key in sorted(values))
    signature = base64.b64encode(
        hmac.new(b"test-auth", canonical.encode(), hashlib.sha1).digest()
    ).decode()

    assert provider.verify_webhook(url, values, signature)
    assert not provider.verify_webhook(url, values, "invalid")


def test_twilio_call_request_encodes_status_events_and_returns_call_id(client, monkeypatch) -> None:
    import httpx

    settings = client.app.state.settings.model_copy(
        update={
            "telephone_provider": "twilio",
            "test_mode": False,
            "twilio_account_sid": SecretStr("AC000"),
            "twilio_auth_token": SecretStr("test-auth"),
            "twilio_from_number": SecretStr("+15005550006"),
            "twilio_to_number": SecretStr("+15005550006"),
            "twilio_public_base_url": "https://calls.example.test",
        }
    )
    provider = TwilioTelephoneProvider(settings)
    monkeypatch.setattr(
        TwilioTelephoneProvider,
        "voice_stream_available",
        property(lambda _: True),
    )
    captured = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured["auth"] = kwargs["auth"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, data):
            captured["url"] = url
            captured["data"] = data
            return httpx.Response(
                201,
                json={"sid": "CA123"},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr("app.calling.providers.telephone.httpx.AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        provider.place_call(CallSession(id=str(uuid4()), status="queued"))
    )

    assert result == "CA123"
    assert [value for key, value in captured["data"] if key == "StatusCallbackEvent"] == [
        "initiated",
        "ringing",
        "answered",
        "completed",
    ]


def test_twilio_transport_timeout_is_unconfirmed_not_a_retryable_failure(
    client,
    monkeypatch,
) -> None:
    import httpx

    from app.calling.providers.telephone import TelephoneCallUncertain

    settings = client.app.state.settings.model_copy(
        update={
            "telephone_provider": "twilio",
            "test_mode": False,
            "twilio_account_sid": SecretStr("AC000"),
            "twilio_auth_token": SecretStr("test-auth"),
            "twilio_from_number": SecretStr("+15005550006"),
            "twilio_to_number": SecretStr("+15005550006"),
            "twilio_public_base_url": "https://calls.example.test",
        }
    )
    provider = TwilioTelephoneProvider(settings)
    monkeypatch.setattr(
        TwilioTelephoneProvider,
        "voice_stream_available",
        property(lambda _: True),
    )

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, *_args, **_kwargs):
            raise httpx.ReadTimeout("request outcome unknown")

    monkeypatch.setattr("app.calling.providers.telephone.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(TelephoneCallUncertain):
        asyncio.run(provider.place_call(CallSession(id=str(uuid4()), status="queued")))


def test_signed_twilio_status_webhook_resolves_an_unconfirmed_call(client) -> None:
    call_id = insert_call(client, "unknown")
    settings = client.app.state.settings.model_copy(
        update={
            "telephone_provider": "twilio",
            "twilio_account_sid": SecretStr("AC000"),
            "twilio_auth_token": SecretStr("test-auth"),
            "twilio_from_number": SecretStr("+15005550006"),
            "twilio_to_number": SecretStr("+15005550006"),
            "twilio_public_base_url": "https://calls.example.test",
        }
    )
    telephone = TwilioTelephoneProvider(settings)
    client.app.state.calling_telephone = telephone
    url = (
        f"https://calls.example.test/api/calling/webhooks/twilio/status"
        f"?call_id={call_id}"
    )
    values = {"CallSid": "CA123", "CallStatus": "completed", "CallDuration": "124"}
    canonical = url + "".join(key + values[key] for key in sorted(values))
    signature = base64.b64encode(
        hmac.new(b"test-auth", canonical.encode(), hashlib.sha1).digest()
    ).decode()

    response = client.post(
        f"/api/calling/webhooks/twilio/status?call_id={call_id}",
        data=values,
        headers={"X-Twilio-Signature": signature},
    )

    assert response.status_code == 200
    with client.app.state.session_factory() as db:
        session = db.get(CallSession, call_id)
        assert session.external_call_id == "CA123"
        assert session.status == "completed"
        assert session.duration_seconds == 124

        late_values = {"CallSid": "CA123", "CallStatus": "in-progress"}
        late_canonical = url + "".join(
            key + late_values[key] for key in sorted(late_values)
        )
        late_signature = base64.b64encode(
            hmac.new(b"test-auth", late_canonical.encode(), hashlib.sha1).digest()
        ).decode()
        late_response = client.post(
            f"/api/calling/webhooks/twilio/status?call_id={call_id}",
            data=late_values,
            headers={"X-Twilio-Signature": late_signature},
        )
        assert late_response.status_code == 200
        with client.app.state.session_factory() as db:
            assert db.get(CallSession, call_id).status == "completed"


def test_mulaw_conversion_preserves_frame_size() -> None:
    pcm = (b"\x00\x00\xff\x7f\x00\x80" * 10)

    encoded = encode_mulaw(pcm)
    decoded = decode_mulaw(encoded)

    assert len(encoded) == len(pcm) // 2
    assert len(decoded) == len(pcm)


def test_offline_ollama_conversation_uses_local_http_endpoint() -> None:
    import httpx

    requests = []

    async def responder(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "local:latest"}]})
        return httpx.Response(200, json={"message": {"content": "Ready. What's the plan?"}})

    settings = Settings(_env_file=None, ollama_base_url="http://jarvis.local", ollama_model="local")
    client = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    engine = ConversationEngine(settings, client)

    async def conversation() -> tuple[bool, str]:
        available = await engine.is_available()
        reply_text = await engine.reply("morning", [("user", "I slept well.")])
        await engine.close()
        return available, reply_text

    available, reply = asyncio.run(conversation())

    assert available
    assert reply == "Ready. What's the plan?"
    payload = json.loads(requests[1].content)
    assert payload["messages"][0]["role"] == "system"
    assert "witty" in payload["messages"][0]["content"]


@pytest.mark.parametrize(
    ("provider_name", "response_body"),
    [
        (
            "gemini",
            {
                "models": [
                    {
                        "name": "models/gemini-test",
                        "supportedGenerationMethods": ["generateContent"],
                    }
                ]
            },
        ),
        ("groq", {"data": [{"id": "groq-test"}]}),
    ],
)
def test_online_ai_availability_checks_configured_model_without_generation(
    provider_name,
    response_body,
) -> None:
    import httpx

    requests = []

    async def responder(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=response_body)

    settings = Settings(
        _env_file=None,
        ai_provider=provider_name,
        gemini_api_key=SecretStr("gemini-test-key"),
        gemini_model="gemini-test",
        groq_api_key=SecretStr("groq-test-key"),
        groq_model="groq-test",
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    engine = ConversationEngine(settings, client)

    async def check_availability() -> bool:
        available = await engine.is_available()
        await engine.close()
        return available

    available = asyncio.run(check_availability())

    assert available
    assert len(requests) == 1
    assert requests[0].method == "GET"
    if provider_name == "groq":
        assert requests[0].headers["Authorization"] == "Bearer groq-test-key"


def test_groq_conversation_sends_authenticated_request() -> None:
    import httpx

    requests = []

    async def responder(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "At your service."}}]},
        )

    settings = Settings(
        _env_file=None,
        ai_provider="groq",
        groq_api_key=SecretStr("groq-test-key"),
        groq_model="groq-test",
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    engine = ConversationEngine(settings, client)
    reply = asyncio.run(engine.reply("morning", [("user", "What's ahead today?")]))

    assert reply == "At your service."
    assert requests[0].headers["Authorization"] == "Bearer groq-test-key"
