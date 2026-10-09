"""Explicitly synthetic scenarios, not carrier pricing, fiscal rules or homologation evidence."""

import json
from copy import deepcopy
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx

from freight_ecommerce.freight.errors import CONFLICT_MESSAGE

SYNTHETIC_COMPANY_ID = UUID("00000000-0000-4000-8000-000000000002")
SYNTHETIC_ORIGIN = "01001000"
SYNTHETIC_KEY = "synthetic-mock-freight-only"
SYNTHETIC_OFFER = {
    "price_cents": 2590,
    "deadline_days": 3,
    "carrier_name": "Transportadora sintética",
    "private_carrier_id": "00000000-0000-4000-8000-000000000010",
    "rate_table_id": "00000000-0000-4000-8000-000000000011",
    "manual_only": True,
    "demonstration_only": True,
    "price_source": "private_table",
    "carrier_workspace_id": None,
    "calculation_snapshot": {"fixture": "synthetic-not-observed"},
}


class SyntheticQuoteTransport(httpx.AsyncBaseTransport):
    def __init__(self, scenario: str = "quoted"):
        if scenario not in {"quoted", "unavailable", "fiscal_review"}:
            raise ValueError("Unknown synthetic scenario")
        self.scenario = scenario
        self.by_key: dict[str, tuple[dict, dict]] = {}
        self.by_id: dict[str, dict] = {}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v1/freight/quotes":
            payload = json.loads(request.content)
            key = payload["request_key"]
            criteria = {name: value for name, value in payload.items() if name != "request_key"}
            if key in self.by_key:
                old_criteria, envelope = self.by_key[key]
                if old_criteria != criteria:
                    return httpx.Response(
                        422,
                        json={
                            "message": CONFLICT_MESSAGE,
                            "errors": {"request_key": [CONFLICT_MESSAGE]},
                        },
                    )
            else:
                identifier = str(uuid5(NAMESPACE_URL, f"synthetic-packsenvios-quote/{key}"))
                offer = deepcopy(SYNTHETIC_OFFER)
                offer["freight_company_id"] = criteria["freight_company_id"]
                offer["freight_location_id"] = criteria.get("freight_location_id")
                envelope = {
                    "data": {
                        "id": identifier,
                        "status": self.scenario,
                        "criteria": deepcopy(criteria),
                        "options": [offer] if self.scenario == "quoted" else [],
                        "selection": None,
                        "shipment_code": None,
                        "created_at": "2026-10-08T12:00:00+00:00",
                    }
                }
                self.by_key[key] = (deepcopy(criteria), deepcopy(envelope))
                self.by_id[identifier] = deepcopy(envelope)
            return httpx.Response(200, json=deepcopy(envelope))
        if request.method == "GET" and request.url.path.startswith("/api/v1/freight/quotes/"):
            envelope = self.by_id.get(request.url.path.rsplit("/", 1)[-1])
            if envelope is not None:
                criteria = envelope["data"]["criteria"]
                if all(
                    request.url.params.get(field) == criteria.get(field)
                    for field in ("freight_company_id", "freight_location_id")
                ):
                    return httpx.Response(200, json=deepcopy(envelope))
        return httpx.Response(404, json={"message": "Synthetic quote not found"})
