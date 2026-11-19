from app.config import Settings


def test_openai_key_uses_standard_environment_variable(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    settings = Settings(_env_file=None)

    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "test-key"


def test_local_ollama_is_the_default_chat_provider() -> None:
    settings = Settings(_env_file=None)

    assert settings.ai_provider == "ollama"
    assert settings.ollama_model == "llama3.2:1b"


def test_deepseek_settings_use_standard_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-reasoner")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.test")

    settings = Settings(_env_file=None)

    assert settings.deepseek_api_key is not None
    assert settings.deepseek_api_key.get_secret_value() == "test-deepseek-key"
    assert settings.deepseek_model == "deepseek-reasoner"
    assert settings.deepseek_base_url == "https://api.deepseek.test"
