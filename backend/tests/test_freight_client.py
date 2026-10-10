import json
import logging
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import testrunner
from pydantic import ValidationError

from freight_ecommerce.freight.client import PacksenviosClient, build_freight_client
from freight_ecommerce.freight.config import FreightSettings
from freight_ecommerce.freight.errors import CONFLICT_MESSAGE, FreightError, parse_retry_after
from freight_ecommerce.freight.schemas import QuoteRequest
from freight_ecommerce.freight.synthetic import SYNTHETIC_KEY, SyntheticQuoteTransport

FIXTURES = Path(__file__).parent / "fixtures" / "freight"
COMPANY = UUID("00000000-0000-4000-8000-000000000002")
API_KEY = "synthetic-real-test-key-never-public"
REQUEST = {
    "request_key": "00000000-0000-4000-8000-000000000001",
    "origin_postal_code": "01001000",
    "destination_postal_code": "20040002",
    "weight_kg": "1.000",
    "declared_value_cents": 10000,
    "length_cm": 20,
    "width_cm": 15,
    "height_cm": 10,
    "volume_count": 1,
}


def fixture(name="quoted"):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def settings(**overrides):
    return FreightSettings(
        _env_file=None,
        **{
            "mode": "real",
            "base_url": "https://authorized.example.test",
            "api_key": API_KEY,
            "company_id": COMPANY,
            "max_attempts": 2,
            **overrides,
        },
    )


@testrunner.mark.parametrize("scenario", ["quoted", "unavailable", "fiscal_review"])
async def test_post_and_get_contract_headers_body_context_and_optional_fields(scenario):
    calls = []
    location = uuid4()
    body = fixture(scenario)
    body["data"]["criteria"]["freight_location_id"] = str(location)

    def handler(request):
        calls.append(request)
        assert request.headers["Authorization"] == f"Bearer {API_KEY}"
        assert request.headers["Accept"] == "application/json"
        assert request.extensions["timeout"]["connect"] == 3
        if request.method == "POST":
            assert request.url.path == "/api/v1/freight/quotes"
            assert request.headers["Content-Type"] == "application/json"
            payload = json.loads(request.content)
            assert payload["request_key"] == REQUEST["request_key"]
            assert payload["freight_company_id"] == str(COMPANY)
            assert payload["freight_location_id"] == str(location)
            assert type(payload["declared_value_cents"]) is int and payload["weight_kg"] == "1.000"
        else:
            assert request.content == b""
            assert request.url.path == f"/api/v1/freight/quotes/{body['data']['id']}"
            assert dict(request.url.params) == {
                "freight_company_id": str(COMPANY),
                "freight_location_id": str(location),
            }
        return httpx.Response(200, json=body)

    async with PacksenviosClient(
        settings(location_id=location), transport=httpx.MockTransport(handler)
    ) as client:
        result = await client.create_quote(QuoteRequest(**REQUEST))
        assert result.data.status == scenario
        assert result.data.id != UUID(REQUEST["request_key"])
        queried = await client.get_quote(result.data.id)
        assert queried == result and len(calls) == 2
        if scenario == "quoted":
            assert result.data.options[0].price_cents == 2590
            assert result.data.options[0].manual_only is True
            assert not hasattr(result.data.options[0], "id")
            assert not hasattr(client, "contract") and not hasattr(client, "select_quote")
        else:
            assert result.data.options == []  # no invented price/offer fallback


async def test_timeout_retries_exact_prepared_bytes_and_never_regenerates_key(caplog):
    payloads = []
    sleeper = AsyncMock()

    def handler(request):
        payloads.append(request.content)
        if len(payloads) == 1:
            raise httpx.ReadTimeout(f"private diagnostic {API_KEY}", request=request)
        return httpx.Response(200, json=fixture())

    with caplog.at_level(logging.DEBUG):
        async with PacksenviosClient(
            settings(), transport=httpx.MockTransport(handler), sleep=sleeper
        ) as client:
            prepared = client.prepare_quote(QuoteRequest(**{**REQUEST, "weight_kg": "1,0"}))
            result = await client.create_quote(prepared)
    assert payloads == [prepared.payload, prepared.payload]
    assert result.data.status == "quoted"
    assert sleeper.await_count == 1 and API_KEY not in caplog.text


async def test_exhausted_network_error_has_no_request_response_or_raw_exception_context():
    def handler(request):
        raise httpx.ConnectError(f"private {API_KEY}", request=request)

    async with PacksenviosClient(
        settings(max_attempts=1), transport=httpx.MockTransport(handler)
    ) as client:
        with testrunner.raises(FreightError) as error:
            await client.create_quote(QuoteRequest(**REQUEST))
    assert error.value.code == "transport_error"
    assert error.value.__context__ is None and API_KEY not in str(error.value)
    assert not hasattr(error.value, "request") and not hasattr(error.value, "response")


@testrunner.mark.parametrize(
    "status,code",
    [
        (401, "unauthorized"),
        (403, "forbidden"),
        (404, "not_found"),
        (409, "conflict"),
        (422, "validation_error"),
        (429, "rate_limited"),
        (503, "unavailable"),
    ],
)
async def test_http_errors_are_normalized_without_echoing_messages_headers_or_body(
    status, code, caplog
):
    def handler(request):
        logging.getLogger("httpcore.http11").debug("raw headers %s", {"Authorization": API_KEY})
        return httpx.Response(
            status,
            json={
                "message": f"private {API_KEY}",
                "errors": {
                    "destination_postal_code": [f"private {API_KEY}"],
                    API_KEY: ["private"],
                },
            },
            extensions={"reason_phrase": API_KEY.encode()},
        )

    with caplog.at_level(logging.DEBUG):
        async with PacksenviosClient(
            settings(max_attempts=1), transport=httpx.MockTransport(handler)
        ) as client:
            with testrunner.raises(FreightError) as error:
                await client.create_quote(QuoteRequest(**REQUEST))
    assert error.value.http_status == status and error.value.code == code
    assert error.value.fields == ("destination_postal_code",)
    assert API_KEY not in str(error.value) + repr(error.value) + caplog.text
    assert error.value.__context__ is None


@testrunner.mark.parametrize("status", [401, 403, 404, 409, 422, 500])
async def test_nonretryable_status_does_not_sleep_or_repeat(status):
    calls = []
    sleep = AsyncMock()

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="synthetic failure")

    async with PacksenviosClient(
        settings(max_attempts=3), transport=httpx.MockTransport(handler), sleep=sleep
    ) as client:
        with testrunner.raises(FreightError):
            await client.create_quote(QuoteRequest(**REQUEST))
    assert len(calls) == 1 and sleep.await_count == 0


@testrunner.mark.parametrize("status", [429, 503])
async def test_retry_after_seconds_and_http_date_are_respected(status):
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    header = "3" if status == 429 else format_datetime(now + timedelta(seconds=4), usegmt=True)
    sleep = AsyncMock()
    calls = []

    def handler(request):
        calls.append(request.content)
        return (
            httpx.Response(status, headers={"Retry-After": header}, json={"message": "synthetic"})
            if len(calls) == 1
            else httpx.Response(200, json=fixture())
        )

    async with PacksenviosClient(
        settings(), transport=httpx.MockTransport(handler), sleep=sleep, now=lambda: now
    ) as client:
        await client.create_quote(QuoteRequest(**REQUEST))
    assert calls[0] == calls[1]
    sleep.assert_awaited_once_with(3 if status == 429 else 4)


async def test_long_retry_after_is_returned_without_clamping_into_an_early_retry():
    calls = []
    sleep = AsyncMock()

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "3600"})

    async with PacksenviosClient(
        settings(), transport=httpx.MockTransport(handler), sleep=sleep
    ) as client:
        with testrunner.raises(FreightError) as error:
            await client.create_quote(QuoteRequest(**REQUEST))
    assert error.value.retry_after_seconds == 3600
    assert len(calls) == 1 and sleep.await_count == 0


async def test_redirect_does_not_forward_bearer_to_another_host():
    calls = []

    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(302, headers={"Location": "https://different.example.test/collect"})

    async with PacksenviosClient(settings(), transport=httpx.MockTransport(handler)) as client:
        with testrunner.raises(FreightError) as error:
            await client.create_quote(QuoteRequest(**REQUEST))
    assert error.value.http_status == 302 and calls == ["authorized.example.test"]


async def test_mock_mode_is_offline_synthetic_and_replay_and_divergent_422_match_contract():
    observed = []
    server = SyntheticQuoteTransport()

    async def handler(request):
        observed.append(request.headers["Authorization"])
        return await server.handle_async_request(request)

    async with build_freight_client(
        FreightSettings(_env_file=None, api_key=API_KEY), transport=httpx.MockTransport(handler)
    ) as client:
        request = QuoteRequest(**REQUEST)
        first = await client.create_quote(request)
        replay = await client.create_quote(request)
        assert replay == first
        assert (await client.get_quote(first.data.id)) == first
        with testrunner.raises(FreightError) as error:
            await client.create_quote(QuoteRequest(**{**REQUEST, "declared_value_cents": 20000}))
        assert error.value.http_status == 422 and error.value.code == "request_key_conflict"
        assert error.value.fields == ("request_key",) and str(error.value) == CONFLICT_MESSAGE
        with testrunner.raises(FreightError) as lookup:
            await client.get_quote(request.request_key)
        assert lookup.value.http_status == 404
    assert set(observed) == {f"Bearer {SYNTHETIC_KEY}"}
    assert all(API_KEY not in header for header in observed)


@testrunner.mark.parametrize("scenario", ["quoted", "unavailable", "fiscal_review"])
async def test_default_factory_mock_needs_no_credentials_or_network(scenario):
    async with build_freight_client(
        FreightSettings(_env_file=None, mock_scenario=scenario)
    ) as client:
        response = await client.create_quote(QuoteRequest(**REQUEST))
        assert response.data.status == scenario


async def test_optional_flags_are_unknown_not_false_and_extra_snapshot_fields_are_preserved():
    body = fixture()
    body["data"]["options"] = [
        {
            "price_cents": 2590,
            "calculation_snapshot": {"unknown": [1, 2]},
            "future_field": {"version": 2},
        }
    ]
    body["data"]["created_at"] = None
    async with PacksenviosClient(
        settings(), transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    ) as client:
        option = (await client.create_quote(QuoteRequest(**REQUEST))).data.options[0]
    assert option.manual_only is None and option.demonstration_only is None
    assert option.deadline_days is None and option.carrier_name is None
    assert option.calculation_snapshot == {"unknown": [1, 2]}
    assert option.model_dump()["future_field"] == {"version": 2}


async def test_get_accepts_historical_status_and_selection_without_a_closed_enum():
    body = fixture("unavailable")
    body["data"]["status"] = "selected"
    body["data"]["selection"] = {"price_snapshot_id": str(uuid4()), "price_cents": 2590}
    async with PacksenviosClient(
        settings(), transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    ) as client:
        result = await client.get_quote(UUID(body["data"]["id"]))
    assert result.data.status == "selected" and result.data.selection.price_cents == 2590


@testrunner.mark.parametrize(
    "kind",
    [
        "quoted_empty",
        "missing_price",
        "float_price",
        "wrong_company",
        "missing_options",
        "criteria_key",
    ],
)
async def test_inconsistent_responses_are_protocol_errors_not_fallback_offers(kind):
    body = fixture()
    if kind == "quoted_empty":
        body["data"]["options"] = []
    elif kind == "missing_price":
        body["data"]["options"][0].pop("price_cents")
    elif kind == "float_price":
        body["data"]["options"][0]["price_cents"] = 25.90
    elif kind == "wrong_company":
        body["data"]["criteria"]["freight_company_id"] = str(uuid4())
    elif kind == "missing_options":
        body["data"].pop("options")
    else:
        body["data"]["criteria"]["request_key"] = REQUEST["request_key"]
    async with PacksenviosClient(
        settings(), transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    ) as client:
        with testrunner.raises(FreightError) as error:
            await client.create_quote(QuoteRequest(**REQUEST))
    assert error.value.code == "invalid_response" and error.value.__context__ is None


def test_prepared_quote_is_immutable_canonical_and_nested_inputs_do_not_change_it():
    client = PacksenviosClient(
        settings(), transport=httpx.MockTransport(lambda req: httpx.Response(200))
    )
    original = {
        **REQUEST,
        "weight_kg": "01,0",
        "destination_postal_code": "20040-002",
        "volumes": [
            {"weight_grams": 1000, "length_cm": 20, "width_cm": 15, "height_cm": 10},
        ],
    }
    request = QuoteRequest(**original)
    prepared = client.prepare_quote(request)
    original["volumes"][0]["weight_grams"] = 2000
    assert json.loads(prepared.payload)["weight_kg"] == "1.000"
    assert json.loads(prepared.payload)["destination_postal_code"] == "20040002"
    assert json.loads(prepared.payload)["volumes"][0]["weight_grams"] == 1000
    with testrunner.raises(FrozenInstanceError):
        prepared.payload = b"mutated"
    with testrunner.raises(ValidationError):
        request.volumes[0].weight_grams = 1
    canonical_request = QuoteRequest(**{**REQUEST, "volumes": list(request.volumes)})
    assert client.prepare_quote(canonical_request) == prepared


async def test_prepared_quote_cannot_be_tampered_and_context_is_backend_fixed():
    calls = []
    async with PacksenviosClient(
        settings(), transport=httpx.MockTransport(lambda req: calls.append(req))
    ) as client:
        for fields in [{"freight_company_id": uuid4()}, {"freight_location_id": uuid4()}]:
            with testrunner.raises(ValueError, match="configured backend context"):
                await client.create_quote(QuoteRequest(**{**REQUEST, **fields}))
        prepared = client.prepare_quote(QuoteRequest(**REQUEST))
        with testrunner.raises(ValueError, match="canonical backend context"):
            await client.create_quote(replace(prepared, criteria_fingerprint="a" * 64))
    assert calls == []


@testrunner.mark.parametrize(
    "changes",
    [
        {"weight_kg": "0"},
        {"weight_kg": "50000.001"},
        {"weight_kg": 1.0},
        {"weight_kg": "1.0000"},
        {"declared_value_cents": 10.1},
        {"declared_value_cents": True},
        {"declared_value_cents": -1},
        {"length_cm": 301},
        {"height_cm": None},
        {"volume_count": None},
        {"destination_postal_code": 20040002},
        {"destination_postal_code": "000"},
        {"modal": "invented"},
        {"invoice_count": 1001},
        {"workspace_id": str(uuid4())},
        {"volumes": [{"weight_grams": 999, "length_cm": 20, "width_cm": 15, "height_cm": 10}]},
        {
            "volumes": [
                {"weight_grams": 1000, "length_cm": 20, "width_cm": 15, "height_cm": 10, "extra": 1}
            ]
        },
    ],
)
def test_invalid_contract_criteria_are_rejected_before_http(changes):
    with testrunner.raises(ValidationError):
        QuoteRequest(**{**REQUEST, **changes})


@testrunner.mark.parametrize(
    "base",
    [
        "http://external.example.test",
        "https://user:password@example.test",
        "https://example.test?key=private",
        "https://example.test#private",
        "https://example.test/api/v1/freight",
        "https://example.test/api/v1/freight/quotes",
    ],
)
def test_base_url_configuration_rejects_unsafe_or_wrong_application_roots(base):
    with testrunner.raises(ValidationError):
        settings(base_url=base)


def test_real_configuration_requires_url_key_company_and_masks_credential_validation():
    for missing in ("base_url", "api_key", "company_id"):
        with testrunner.raises(ValidationError):
            settings(**{missing: None if missing != "api_key" else ""})
    with testrunner.raises(ValidationError) as error:
        settings(base_url=f"https://example.test/{API_KEY}")
    assert API_KEY not in str(error.value)
    assert API_KEY not in repr(settings()) and API_KEY not in settings().model_dump_json()
    assert settings(base_url="http://127.0.0.1:8080/").base_url == "http://127.0.0.1:8080"


async def test_library_log_filter_does_not_change_unrelated_logs(caplog):
    async with build_freight_client(FreightSettings(_env_file=None)) as client:
        await client.create_quote(QuoteRequest(**REQUEST))
    with caplog.at_level(logging.INFO):
        logging.getLogger("httpx").info("ordinary unrelated diagnostic")
    assert "ordinary unrelated diagnostic" in caplog.text


async def test_timeout_after_server_persistence_replays_original_quote_not_new_scenario():
    server = SyntheticQuoteTransport("quoted")
    calls = []

    async def handler(request):
        calls.append(request.content)
        response = await server.handle_async_request(request)
        if len(calls) == 1:
            server.scenario = "unavailable"
            raise httpx.ReadTimeout("Synthetic response lost after persistence", request=request)
        return response

    async with build_freight_client(
        FreightSettings(_env_file=None), transport=httpx.MockTransport(handler), sleep=AsyncMock()
    ) as client:
        result = await client.create_quote(QuoteRequest(**REQUEST))
        assert result.data.status == "quoted" and result.data.options[0].price_cents == 2590
        assert len(server.by_id) == 1 and calls[0] == calls[1]


async def test_real_company_without_units_requires_origin_and_location_can_resolve_it():
    no_origin = {key: value for key, value in REQUEST.items() if key != "origin_postal_code"}
    async with PacksenviosClient(
        settings(), transport=httpx.MockTransport(lambda req: httpx.Response(200))
    ) as client:
        with testrunner.raises(ValueError, match="explicit origin"):
            client.prepare_quote(QuoteRequest(**no_origin))
    location = uuid4()
    async with PacksenviosClient(
        settings(location_id=location),
        transport=httpx.MockTransport(lambda req: httpx.Response(200)),
    ) as client:
        payload = json.loads(client.prepare_quote(QuoteRequest(**no_origin)).payload)
        assert (
            payload["freight_location_id"] == str(location) and "origin_postal_code" not in payload
        )


def test_weight_only_and_invoice_count_and_volume_count_rules_follow_simple_quote_contract():
    weight_only = QuoteRequest(
        **{
            key: value
            for key, value in REQUEST.items()
            if key not in {"length_cm", "width_cm", "height_cm", "volume_count"}
        },
        invoice_count=0,
    )
    assert "length_cm" not in json.loads(weight_only.canonical_bytes())
    assert json.loads(weight_only.canonical_bytes())["invoice_count"] == 0
    with testrunner.raises(ValidationError, match="volume count"):
        QuoteRequest(
            **{
                **REQUEST,
                "volume_count": 2,
                "volumes": [
                    {"weight_grams": 1000, "length_cm": 20, "width_cm": 15, "height_cm": 10},
                ],
            }
        )


@testrunner.mark.parametrize(
    "value,expected", [("0", 0), ("-1", None), ("later", None), ("1.5", None)]
)
def test_retry_after_invalid_values_do_not_become_negative_or_fractional_waits(value, expected):
    assert parse_retry_after(value, datetime(2026, 10, 8, 12, tzinfo=UTC)) == expected


async def test_retry_wait_budget_is_total_not_a_reason_to_retry_early():
    calls = []
    sleep = AsyncMock()

    def handler(request):
        calls.append(request.content)
        return httpx.Response(429, headers={"Retry-After": "3"})

    async with PacksenviosClient(
        settings(max_attempts=3, max_retry_wait_seconds=5),
        transport=httpx.MockTransport(handler),
        sleep=sleep,
    ) as client:
        with testrunner.raises(FreightError) as error:
            await client.create_quote(QuoteRequest(**REQUEST))
    assert len(calls) == 2 and calls[0] == calls[1]
    assert error.value.retry_after_seconds == 3
    sleep.assert_awaited_once_with(3)
