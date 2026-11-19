from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "JARVIS_OPENAI_API_KEY"),
    )
    openai_model: str = Field(
        default="gpt-4.1-mini",
        validation_alias=AliasChoices("OPENAI_MODEL", "JARVIS_OPENAI_MODEL"),
    )
    database_url: str = "sqlite:///../data/jarvis.db"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    calling_access_token: SecretStr | None = None
    default_timezone: str = "Africa/Nairobi"
    call_ring_timeout_seconds: int = Field(default=30, ge=5, le=180)
    require_https: bool = False
    test_mode: bool = True
    ai_provider: str = Field(default="ollama", validation_alias="JARVIS_AI_PROVIDER")
    default_ai_provider: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEFAULT_AI_PROVIDER", "JARVIS_AI_PROVIDER"),
    )
    ai_fallback_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("AI_FALLBACK_ENABLED", "JARVIS_AI_FALLBACK_ENABLED"),
    )
    ai_request_timeout: float = Field(
        default=60,
        gt=0,
        le=300,
        validation_alias=AliasChoices("AI_REQUEST_TIMEOUT", "JARVIS_AI_REQUEST_TIMEOUT"),
    )
    ollama_base_url: str = Field(
        default="http://127.0.0.1:11434",
        validation_alias=AliasChoices("OLLAMA_BASE_URL", "JARVIS_OLLAMA_BASE_URL"),
    )
    ollama_model: str = Field(
        default="llama3.2:1b",
        validation_alias=AliasChoices("OLLAMA_MODEL", "JARVIS_OLLAMA_MODEL"),
    )
    gemini_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "JARVIS_GEMINI_API_KEY"),
    )
    gemini_model: str = Field(
        default="gemini-3.8-flash",
        validation_alias=AliasChoices("GEMINI_MODEL", "JARVIS_GEMINI_MODEL"),
    )
    deepseek_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("DEEPSEEK_API_KEY", "JARVIS_DEEPSEEK_API_KEY"),
    )
    deepseek_model: str = Field(
        default="deepseek-chat",
        validation_alias=AliasChoices("DEEPSEEK_MODEL", "JARVIS_DEEPSEEK_MODEL"),
    )
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        validation_alias=AliasChoices("DEEPSEEK_BASE_URL", "JARVIS_DEEPSEEK_BASE_URL"),
    )
    monthly_spending_limit: float | None = Field(default=None, ge=0)
    ai_pricing_json: str = Field(default="", validation_alias="AI_PRICING_JSON")
    debug: bool = Field(default=False, validation_alias=AliasChoices("DEBUG", "JARVIS_DEBUG"))
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    twilio_account_sid: SecretStr | None = None
    twilio_auth_token: SecretStr | None = None
    twilio_from_number: SecretStr | None = None
    twilio_to_number: SecretStr | None = None
    twilio_public_base_url: str | None = None
    telephone_provider: str = "none"
    stun_servers: list[str] = ["stun:stun.l.google.com:19302"]
    turn_server: str | None = None
    turn_username: SecretStr | None = None
    turn_credential: SecretStr | None = None
    whisper_model_size: str = "small"
    speech_recognition_provider: str = "vosk"
    vosk_model_path: Path | None = None
    wake_word_model_path: Path | None = None
    wake_word_phrase: str = "Hello JARVIS Scott here"
    piper_binary: str = "piper"
    piper_model_path: Path | None = None
    piper_length_scale: float = Field(default=1.0, gt=0.25, le=3.0)

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="JARVIS_",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def effective_ai_provider(self) -> str:
        return (self.default_ai_provider or self.ai_provider).lower().strip()

    def resolved_database_url(self) -> str:
        if not self.database_url.startswith("sqlite:///"):
            return self.database_url

        database_path = self.database_url.removeprefix("sqlite:///")
        if database_path == ":memory:" or database_path.startswith("/"):
            return self.database_url

        absolute_path = (BACKEND_DIR / database_path).resolve()
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{absolute_path}"

    @property
    def telephone_credentials_configured(self) -> bool:
        return all(
            value is not None and bool(value.get_secret_value().strip())
            for value in (
                self.twilio_account_sid,
                self.twilio_auth_token,
                self.twilio_from_number,
                self.twilio_to_number,
            )
        ) and bool(self.twilio_public_base_url)

    @property
    def calling_auth_configured(self) -> bool:
        return (
            self.calling_access_token is not None
            and len(self.calling_access_token.get_secret_value()) >= 32
        )

    @property
    def voice_stack_configured(self) -> bool:
        try:
            from importlib.util import find_spec

            return (
                find_spec("aiortc") is not None
                and find_spec("faster_whisper") is not None
                and self.piper_model_path is not None
                and self.piper_model_path.is_file()
            )
        except (ImportError, ValueError):
            return False


@lru_cache
def get_settings() -> Settings:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env", override=False)
    return Settings()
