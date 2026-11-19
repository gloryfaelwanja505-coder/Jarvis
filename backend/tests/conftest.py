from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    settings = Settings(
        openai_api_key=SecretStr("test-key"),
        calling_access_token=SecretStr("test-calling-token-that-is-at-least-32-chars"),
        ai_provider="openai",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        _env_file=None,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
