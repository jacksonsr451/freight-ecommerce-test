import logging
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest

from freight_ecommerce.freight.client import PacksenviosClient
from freight_ecommerce.freight.config import FreightSettings
from freight_ecommerce.freight.errors import FreightError
from freight_ecommerce.freight.schemas import QuoteRequest

KEY = "synthetic-protocol-test-secret"
COMPANY = UUID("00000000-0000-4000-8000-000000000002")
QUOTE_ID = UUID("00000000-0000-4000-8000-000000000003")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def settings():
    return FreightSettings(
        _env_file=None,
        mode="real",
        base_url="https://example.test/prefix",
        api_key=KEY,
        company_id=COMPANY,
    )


@pytest.mark.anyio
async def test_malformed_json_is_not_retried_or_exposed_in_error_logs(caplog):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, text=f"malformed private {KEY}")

    with caplog.at_level(logging.DEBUG):
        async with PacksenviosClient(settings(), transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(FreightError) as error:
                await client.create_quote(
                    QuoteRequest(
                        request_key=UUID(int=1),
                        origin_postal_code="01001000",
                        destination_postal_code="20040002",
                        weight_kg="1.000",
                        declared_value_cents=10000,
                    )
                )
    assert len(calls) == 1 and error.value.code == "invalid_response"
    assert error.value.http_status == 200 and error.value.__context__ is None
    assert KEY not in caplog.text + str(error.value)


@pytest.mark.anyio
async def test_get_timeout_reuses_uuid_context_and_application_prefix_without_a_body():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("synthetic", request=request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "id": str(QUOTE_ID),
                    "status": "unavailable",
                    "criteria": {"freight_company_id": str(COMPANY)},
                    "options": [],
                }
            },
        )

    async with PacksenviosClient(
        settings(), transport=httpx.MockTransport(handler), sleep=AsyncMock()
    ) as client:
        result = await client.get_quote(QUOTE_ID)
    assert result.data.id == QUOTE_ID and len(calls) == 2
    assert all(request.url.path == f"/prefix/api/v1/freight/quotes/{QUOTE_ID}" for request in calls)
    assert all(request.method == "GET" and request.content == b"" for request in calls)
    assert calls[0].url.query == calls[1].url.query
