import pytest
from httpx import ASGITransport, AsyncClient

from freight_ecommerce import main
from freight_ecommerce.config import Settings
from freight_ecommerce.freight.config import FreightSettings


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["mock", "real"])
async def test_public_runtime_exposes_only_mode_and_simulation_without_secrets(monkeypatch, mode):
    key = "synthetic-runtime-secret-never-browser"
    config = FreightSettings(
        _env_file=None,
        mode=mode,
        api_key=key,
        base_url="https://authorized.example.test",
        company_id="00000000-0000-4000-8000-000000000002",
    )
    monkeypatch.setattr(main, "FreightSettings", lambda: config)
    app = main.create_app(Settings(_env_file=None, environment="test"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/runtime")
    assert response.status_code == 200
    assert response.json() == {"freight_mode": mode, "purchases_simulated": True}
    assert key not in response.text and "base_url" not in response.text
    assert app.state.freight_client is None  # no provider client/network created
    app.state.engine.dispose()


@pytest.mark.anyio
async def test_invalid_runtime_configuration_is_safe_error_not_mock_fallback(monkeypatch):
    def invalid():
        raise ValueError("synthetic-private-config-detail")

    monkeypatch.setattr(main, "FreightSettings", invalid)
    app = main.create_app(Settings(_env_file=None, environment="test"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/runtime")
    assert response.status_code == 503 and "synthetic-private" not in response.text
    assert "freight_mode" not in response.json()
    app.state.engine.dispose()
