from collections.abc import Sequence

import httpx

from app.config import Settings
from app.calling.call_personality import CallContext, call_instructions
from app.ai.gemini import GeminiProvider, GeminiError


class AIProviderUnavailable(RuntimeError):
    pass


class ConversationEngine:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client
        self._gemini = GeminiProvider(settings)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def reply(
        self,
        context: CallContext,
        transcript: Sequence[tuple[str, str]],
    ) -> str:
        if not transcript:
            raise ValueError("A conversation turn is required.")
        if self.settings.ai_provider == "ollama":
            content = await self._ollama(context, transcript)
        elif self.settings.ai_provider == "gemini":
            try:
                content, _ = await self._gemini.generate(
                    [{"role": role, "content": content} for role, content in transcript],
                    call_instructions(context),
                )
            except GeminiError as exc:
                raise AIProviderUnavailable(str(exc)) from exc
        elif self.settings.ai_provider == "deepseek":
            content = await self._deepseek(context, transcript)
        elif self.settings.ai_provider == "groq":
            content = await self._openai_compatible(transcript, context)
        else:
            raise AIProviderUnavailable(f"Unsupported AI provider: {self.settings.ai_provider}")
        if not content.strip():
            raise AIProviderUnavailable("The AI provider returned an empty response.")
        return content.strip()

    async def is_available(self) -> bool:
        try:
            if self.settings.ai_provider == "ollama":
                response = await self._http().get(
                    f"{self.settings.ollama_base_url.rstrip('/')}/api/tags",
                    timeout=3.0,
                )
                response.raise_for_status()
                body = response.json()
                models = body.get("models", []) if isinstance(body, dict) else []
                if not isinstance(models, list):
                    return False
                requested_model = self.settings.ollama_model
                return any(
                    isinstance(item, dict)
                    and (
                        str(item.get("name", "")) == requested_model
                        or (
                            ":" not in requested_model
                            and str(item.get("name", "")).split(":")[0] == requested_model
                        )
                    )
                    for item in models
                )
            if self.settings.ai_provider == "gemini":
                models = await self._gemini.list_models()
                return self.settings.gemini_model in models
            if self.settings.ai_provider == "groq":
                if (
                    self.settings.groq_api_key is None
                    or not self.settings.groq_api_key.get_secret_value().strip()
                ):
                    return False
                response = await self._http().get(
                    "https://api.groq.com/openai/v1/models",
                    headers={
                        "Authorization": f"Bearer {self.settings.groq_api_key.get_secret_value()}"
                    },
                    timeout=5.0,
                )
                response.raise_for_status()
                body = response.json()
                models = body.get("data", []) if isinstance(body, dict) else []
                if not isinstance(models, list):
                    return False
                return any(
                    isinstance(item, dict) and item.get("id") == self.settings.groq_model
                    for item in models
                )
            if self.settings.ai_provider == "deepseek":
                if (
                    self.settings.deepseek_api_key is None
                    or not self.settings.deepseek_api_key.get_secret_value().strip()
                ):
                    return False
                response = await self._http().get(
                    f"{self.settings.deepseek_base_url.rstrip('/')}/models",
                    headers={
                        "Authorization": f"Bearer {self.settings.deepseek_api_key.get_secret_value()}"
                    },
                    timeout=5.0,
                )
                response.raise_for_status()
                body = response.json()
                models = body.get("data", []) if isinstance(body, dict) else []
                if not isinstance(models, list):
                    return False
                return any(
                    isinstance(item, dict) and item.get("id") == self.settings.deepseek_model
                    for item in models
                )
        except (httpx.HTTPError, ValueError):
            return False
        return False

    async def summarize(self, transcript: str) -> str:
        if not transcript.strip():
            return ""
        prompt = (
            "Summarize this personal-assistant call in 2-4 concise sentences. "
            "Include completed tasks, unfinished priorities, and agreed next steps. "
            "Do not invent details.\n\n"
            f"Transcript:\n{transcript[:30_000]}"
        )
        return await self.reply("evening", [("user", prompt)])

    async def _ollama(
        self,
        context: CallContext,
        transcript: Sequence[tuple[str, str]],
    ) -> str:
        try:
            response = await self._http().post(
                f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.settings.ollama_model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": call_instructions(context)},
                        *[{"role": role, "content": content} for role, content in transcript],
                    ],
                    "options": {"temperature": 0.7},
                },
                timeout=60.0,
            )
            response.raise_for_status()
            return str(response.json()["message"]["content"])
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise AIProviderUnavailable("The configured Ollama model is unavailable.") from exc

    async def _deepseek(
        self,
        context: CallContext,
        transcript: Sequence[tuple[str, str]],
    ) -> str:
        if (
            self.settings.deepseek_api_key is None
            or not self.settings.deepseek_api_key.get_secret_value().strip()
        ):
            raise AIProviderUnavailable("DeepSeek is not configured.")
        try:
            response = await self._http().post(
                f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.deepseek_api_key.get_secret_value()}"
                },
                json={
                    "model": self.settings.deepseek_model,
                    "messages": [
                        {"role": "system", "content": call_instructions(context)},
                        *[{"role": role, "content": content} for role, content in transcript],
                    ],
                    "temperature": 0.7,
                    "stream": False,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderUnavailable("DeepSeek could not complete the request.") from exc

    async def _openai_compatible(
        self,
        transcript: Sequence[tuple[str, str]],
        context: CallContext,
    ) -> str:
        if (
            self.settings.groq_api_key is None
            or not self.settings.groq_api_key.get_secret_value().strip()
        ):
            raise AIProviderUnavailable("Groq is not configured.")
        try:
            response = await self._http().post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.groq_api_key.get_secret_value()}"},
                json={
                    "model": self.settings.groq_model,
                    "messages": [
                        {"role": "system", "content": call_instructions(context)},
                        *[{"role": role, "content": content} for role, content in transcript],
                    ],
                    "temperature": 0.7,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderUnavailable("Groq could not complete the request.") from exc

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client
