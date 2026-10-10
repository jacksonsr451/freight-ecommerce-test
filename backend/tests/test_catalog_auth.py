import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from freight_ecommerce.catalog import router, seed
from freight_ecommerce.config import Settings
from freight_ecommerce.main import create_app

ADMIN_KEY = "synthetic-local-admin-key-for-tests-only"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "environment,key,header,status",
    [
        ("test", ADMIN_KEY, None, 401),
        ("test", ADMIN_KEY, "incorrect-key", 401),
        ("development", "", ADMIN_KEY, 403),
        ("production", ADMIN_KEY, ADMIN_KEY, 403),
    ],
)
async def test_admin_is_restricted_even_without_running_database(environment, key, header, status):
    settings = Settings(_env_file=None, environment=environment, LOCAL_ADMIN_KEY=key)
    app = create_app(settings)
    headers = {"X-Local-Admin-Key": header} if header else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for method, path in [
            ("GET", "/api/admin/products"),
            ("GET", "/api/admin/products/00000000-0000-4000-8000-000000000001"),
            ("POST", "/api/admin/products"),
            ("PATCH", "/api/admin/products/00000000-0000-4000-8000-000000000001"),
            ("DELETE", "/api/admin/products/00000000-0000-4000-8000-000000000001"),
            ("GET", "/api/admin/orders"),
            ("GET", "/api/admin/orders/00000000-0000-4000-8000-000000000001"),
            ("POST", "/api/admin/orders/00000000-0000-4000-8000-000000000001/fulfillment"),
            ("GET", "/api/admin/imports/availability"),
            ("GET", "/api/admin/imports/export-readiness"),
            ("GET", "/api/admin/imports"),
            ("GET", "/api/admin/imports/00000000-0000-4000-8000-000000000001"),
        ]:
            response = await client.request(method, path, headers=headers)
            assert response.status_code == status
            assert ADMIN_KEY not in response.text
    app.state.engine.dispose()


@pytest.mark.anyio
async def test_internal_openapi_documents_only_local_admin_key_not_external_secret(monkeypatch):
    external_secret = "synthetic-external-freight-secret-never-public"
    monkeypatch.setenv("FREIGHT_API_KEY", external_secret)
    app = create_app(Settings(_env_file=None, environment="test", LOCAL_ADMIN_KEY=ADMIN_KEY))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert not schema["paths"]["/api/products"]["get"].get("security")
        assert schema["paths"]["/api/admin/products"]["post"]["security"] == [{"LocalAdminKey": []}]
        assert schema["paths"]["/api/admin/orders"]["get"]["security"] == [{"LocalAdminKey": []}]
        assert schema["paths"]["/api/admin/orders/{order_id}/fulfillment"]["post"]["security"] == [
            {"LocalAdminKey": []}
        ]
        assert schema["paths"]["/api/admin/imports"]["post"]["security"] == [{"LocalAdminKey": []}]
        assert schema["paths"]["/api/admin/imports/{batch_id}/confirm"]["post"]["security"] == [
            {"LocalAdminKey": []}
        ]
        assert (
            schema["components"]["securitySchemes"]["LocalAdminKey"]["name"] == "X-Local-Admin-Key"
        )
        assert "201" in schema["paths"]["/api/admin/products"]["post"]["responses"]
        assert (
            "409" in schema["paths"]["/api/products/{product_id}/stock-check"]["post"]["responses"]
        )
        assert schema["components"]["schemas"]["ProductCreate"]["additionalProperties"] is False
        assert (
            schema["components"]["schemas"]["ProductCreate"]["properties"]["price_cents"]["type"]
            == "integer"
        )
        assert schema["components"]["schemas"]["ProductPatch"]["minProperties"] == 1
        assert (
            schema["components"]["schemas"]["ProductPatch"]["properties"]["price_cents"]["type"]
            == "integer"
        )
        assert ADMIN_KEY not in response.text and external_secret not in response.text
    app.state.engine.dispose()


def test_short_admin_key_is_rejected_without_echoing_secret():
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, LOCAL_ADMIN_KEY="synthetic-short-secret")
    assert "synthetic-short-secret" not in str(error.value)


@pytest.mark.anyio
async def test_unavailable_database_returns_normalized_error_without_private_details():
    app = create_app(Settings(_env_file=None, environment="test"))

    def unavailable():
        raise OperationalError("synthetic-private-sql", {}, RuntimeError("synthetic-private-error"))

    app.dependency_overrides[router.get_session] = unavailable
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/products")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "database_unavailable"
    assert "synthetic-private" not in response.text
    app.state.engine.dispose()


@pytest.mark.parametrize(
    "environment,url",
    [
        ("production", "postgresql+psycopg://synthetic@127.0.0.1/demo"),
        ("development", "postgresql+psycopg://synthetic@example.test/demo"),
    ],
)
def test_seed_refuses_production_and_remote_database_before_connecting(
    monkeypatch, environment, url
):
    settings = Settings(_env_file=None, environment=environment, DATABASE_URL=url)
    monkeypatch.setattr(seed, "Settings", lambda: settings)

    def no_connection(*args, **kwargs):
        pytest.fail("Seed must not construct an engine for a refused environment")

    monkeypatch.setattr(seed, "build_engine", no_connection)
    with pytest.raises(RuntimeError, match="local PostgreSQL"):
        seed.main()
