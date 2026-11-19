from app.ai.ollama_client import OllamaClient, OllamaUnavailable
from app.config import Settings


class ProviderManager:
    def __init__(self, settings: Settings, ollama: OllamaClient | None = None) -> None:
        self.settings = settings
        self.ollama = ollama or OllamaClient(settings)

    async def local_models(self) -> list[str]:
        return await self.ollama.list_models()

    async def select_local_model(self, model: str) -> str:
        if not model.strip():
            raise ValueError("Choose a model name.")
        models = await self.local_models()
        if model not in models:
            raise OllamaUnavailable("That model is not installed in Ollama.")
        self.settings.ollama_model = model
        return model
