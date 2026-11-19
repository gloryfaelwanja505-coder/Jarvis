import asyncio
import json

import httpx

from app.config import Settings
from app.ai.ai_manager import AIManager
from app.services import ai


def install_transport(monkeypatch, handler) -> list[httpx.Request]:
    requests: list[httpx.Request] = []
    async_client = httpx.AsyncClient

    def create_client(*args, **kwargs):
        def capture(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return handler(request)

        return async_client(*args, transport=httpx.MockTransport(capture), **kwargs)

    monkeypatch.setattr(ai.httpx, "AsyncClient", create_client)
    return requests


def test_ollama_chat_uses_configured_model_and_jarvis_instructions(monkeypatch) -> None:
    requests = install_transport(
        monkeypatch,
        lambda _: httpx.Response(200, json={"message": {"content": "Hello."}}),
    )
    settings = Settings(
        _env_file=None,
        ai_provider="ollama",
        ollama_base_url="http://ollama.test",
        ollama_model="llama3.2:1b",
    )

    reply = asyncio.run(ai.ollama_chat(settings, [("user", "Hi.")]))

    payload = json.loads(requests[0].content)
    assert reply == "Hello."
    assert requests[0].url == "http://ollama.test/api/chat"
    assert payload["model"] == "llama3.2:1b"
    assert payload["stream"] is False
    assert payload["messages"][0]["role"] == "system"
    assert "Never claim that you performed an external action." in payload["messages"][0]["content"]


def test_ollama_stream_yields_text_deltas(monkeypatch) -> None:
    body = (
        b'{"message":{"content":"Local "},"done":false}\n'
        b'{"message":{"content":"reply."},"done":true}\n'
    )
    requests = install_transport(monkeypatch, lambda _: httpx.Response(200, content=body))
    settings = Settings(_env_file=None, ai_provider="ollama")

    async def collect() -> list[str]:
        return [part async for part in ai.stream_ollama_chat(settings, [("user", "Hi.")])]

    assert asyncio.run(collect()) == ["Local ", "reply."]
    payload = json.loads(requests[0].content)
    assert requests[0].url == "http://127.0.0.1:11434/api/chat"
    assert payload["model"] == "llama3.2:1b"
    assert payload["stream"] is True


def test_ai_manager_adds_personality_and_approved_preferences() -> None:
    class FakeOllama:
        async def generate(self, messages, model=None):
            return messages[0]["content"]

        async def stream(self, messages, model=None):
            yield messages[0]["content"]

    manager = AIManager(Settings(_env_file=None), ollama=FakeOllama())
    manager.personality = "Thoughtful and concise."

    async def verify() -> str:
        return await manager.generate([("user", "Remember my tea.")], [("tea", "peppermint")])

    prompt = asyncio.run(verify())
    assert "Thoughtful and concise." in prompt
    assert "tea: peppermint" in prompt
    assert "Never claim that you performed an external action." in prompt
