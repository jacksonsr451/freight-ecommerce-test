import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from freight_ecommerce.config import Settings
from freight_ecommerce.main import create_app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_local_health_and_openapi_do_not_expose_backend_secret(monkeypatch):
    sentinel = "synthetic-test-secret-never-public"
    monkeypatch.setenv("FREIGHT_API_KEY", sentinel)
    app = create_app(Settings(_env_file=None, environment="test"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "freight-ecommerce-test"}
        schema = await client.get("/openapi.json")
        assert schema.status_code == 200
        assert set(schema.json()["paths"]) == {"/api/health"}
        assert sentinel not in response.text + schema.text


def test_settings_use_environment_and_reject_invalid_value(monkeypatch):
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    assert Settings(_env_file=None).environment == "test"
    monkeypatch.setenv("APP_ENVIRONMENT", "invalid")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
