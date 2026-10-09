import asyncio
import hashlib
import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

import httpx

from freight_ecommerce.freight.config import FreightSettings
from freight_ecommerce.freight.errors import (
    CONFLICT_MESSAGE,
    MESSAGES,
    FreightError,
    parse_retry_after,
)
from freight_ecommerce.freight.logging import protect_transport_logs, transport_logging_scope
from freight_ecommerce.freight.schemas import PreparedQuote, QuoteEnvelope, QuoteRequest
from freight_ecommerce.freight.synthetic import (
    SYNTHETIC_COMPANY_ID,
    SYNTHETIC_KEY,
    SYNTHETIC_ORIGIN,
    SyntheticQuoteTransport,
)

logger = logging.getLogger(__name__)


class PacksenviosClient:
    """Only documented simple quote POST/GET. Does not expose a route to browsers."""

    def __init__(
        self,
        settings: FreightSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.settings = settings
        self._sleep = sleep
        self._now = now
        self._company = settings.company_id
        self._origin = settings.origin_postal_code
        if settings.mode == "mock":
            self._company = self._company or SYNTHETIC_COMPANY_ID
            self._origin = self._origin or SYNTHETIC_ORIGIN
            transport = (
                transport
                if transport is not None
                else SyntheticQuoteTransport(settings.mock_scenario)
            )
            self._base = "https://packsenvios.mock.invalid"
            key = SYNTHETIC_KEY  # Never send an environment's real key in mock mode.
        else:
            self._base = settings.base_url
            key = settings.api_key.get_secret_value()
        protect_transport_logs()
        self._http = httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(
                settings.timeout_seconds, connect=settings.connect_timeout_seconds
            ),
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    @property
    def integration_scope(self) -> str:
        """Local organization/environment namespace; never a request tenant selector or key hash."""
        value = json.dumps(
            {
                "mode": self.settings.mode,
                "base": self._base,
                "organization": self.settings.integration_scope,
            },
            sort_keys=True,
        )
        return f"{self.settings.mode}:{hashlib.sha256(value.encode()).hexdigest()}"

    def prepare_quote(self, request: QuoteRequest) -> PreparedQuote:
        if request.freight_company_id is not None and request.freight_company_id != self._company:
            raise ValueError("Quote company differs from the configured backend context")
        if (
            request.freight_location_id is not None
            and request.freight_location_id != self.settings.location_id
        ):
            raise ValueError("Quote location differs from the configured backend context")
        data = request.model_dump(mode="json", exclude_none=True)
        data["freight_company_id"] = str(self._company)
        if self.settings.location_id is not None:
            data["freight_location_id"] = str(self.settings.location_id)
        if request.origin_postal_code is None and self._origin is not None:
            data["origin_postal_code"] = self._origin
        bound = QuoteRequest.model_validate(data)
        if bound.origin_postal_code is None and bound.freight_location_id is None:
            raise ValueError("Quote needs an explicit origin or a configured location")
        payload = bound.canonical_bytes()
        criteria = bound.model_dump(mode="json", exclude={"request_key"}, exclude_none=True)
        digest = hashlib.sha256(
            json.dumps(criteria, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return PreparedQuote(bound.request_key, payload, digest)

    async def create_quote(self, request: QuoteRequest | PreparedQuote) -> QuoteEnvelope:
        if isinstance(request, QuoteRequest):
            prepared = self.prepare_quote(request)
        else:
            prepared = self.prepare_quote(QuoteRequest.model_validate_json(request.payload))
            if prepared != request:
                raise ValueError("Prepared request does not match its canonical backend context")
        return await self._send("POST", "/api/v1/freight/quotes", prepared.payload)

    async def get_quote(self, quote_request_id: UUID) -> QuoteEnvelope:
        identifier = UUID(str(quote_request_id))
        params = {"freight_company_id": str(self._company)}
        if self.settings.location_id is not None:
            params["freight_location_id"] = str(self.settings.location_id)
        return await self._send("GET", f"/api/v1/freight/quotes/{identifier}", params=params)

    def _response_context_matches(self, result: QuoteEnvelope) -> bool:
        for field, configured in (
            ("freight_company_id", self._company),
            ("freight_location_id", self.settings.location_id),
        ):
            returned = result.data.criteria.get(field)
            if configured is not None and returned is not None:
                try:
                    if UUID(str(returned)) != configured:
                        return False
                except ValueError:
                    return False
        return True

    def _http_error(self, response: httpx.Response) -> FreightError:
        code, message = MESSAGES.get(
            response.status_code, ("unexpected_status", "Resposta HTTP de frete inesperada.")
        )
        fields = ()
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and isinstance(body.get("errors"), dict):
            errors = body["errors"]
            fields = tuple(
                sorted(
                    name
                    for name in errors
                    if name in QuoteRequest.model_fields
                    or re.fullmatch(
                        r"volumes\.[0-9]+\.(weight_grams|length_cm|width_cm|height_cm)", name
                    )
                )
            )
            request_errors = errors.get("request_key")
            if (
                response.status_code == 422
                and isinstance(request_errors, list)
                and CONFLICT_MESSAGE in request_errors
            ):
                code, message = "request_key_conflict", CONFLICT_MESSAGE
        return FreightError(
            code,
            message,
            http_status=response.status_code,
            fields=fields,
            retry_after_seconds=parse_retry_after(response.headers.get("Retry-After"), self._now()),
        )

    async def _send(self, method, path, content=None, *, params=None) -> QuoteEnvelope:
        waited = 0.0
        for attempt in range(1, self.settings.max_attempts + 1):
            failure = None
            response = None
            scope = transport_logging_scope.set(True)
            try:
                response = await self._http.request(
                    method,
                    self._base + path,
                    content=content,
                    params=params,
                    headers={"Content-Type": "application/json"} if method == "POST" else None,
                )
            except httpx.TimeoutException:
                failure = FreightError("timeout", "Tempo de espera da cotação excedido.")
            except httpx.RequestError:
                failure = FreightError(
                    "transport_error", "Falha de comunicação com o serviço de frete."
                )
            finally:
                transport_logging_scope.reset(scope)
            if response is not None:
                if response.status_code == 200:
                    try:
                        result = QuoteEnvelope.model_validate(response.json())
                        if not self._response_context_matches(result):
                            raise ValueError("Unexpected response context")
                    except ValueError:
                        failure = FreightError(
                            "invalid_response",
                            "Resposta de cotação fora do contrato documentado.",
                            http_status=200,
                        )
                    else:
                        logger.info(
                            "freight operation=%s attempt=%d outcome=success status=200",
                            method,
                            attempt,
                        )
                        return result
                else:
                    failure = self._http_error(response)
            logger.info(
                "freight operation=%s attempt=%d outcome=%s status=%s",
                method,
                attempt,
                failure.code,
                failure.http_status,
            )
            retryable = failure.code in {"timeout", "transport_error"} or failure.http_status in {
                429,
                503,
            }
            delay = (
                failure.retry_after_seconds
                if failure.retry_after_seconds is not None
                else 0.1 * 2 ** (attempt - 1)
            )
            if (
                not retryable
                or attempt == self.settings.max_attempts
                or waited + delay > self.settings.max_retry_wait_seconds
            ):
                raise failure from None
            await self._sleep(delay)  # POST reuses the exact same immutable bytes/request_key.
            waited += delay
        raise RuntimeError("Unreachable retry state")


def build_freight_client(settings: FreightSettings | None = None, **kwargs) -> PacksenviosClient:
    return PacksenviosClient(settings if settings is not None else FreightSettings(), **kwargs)
