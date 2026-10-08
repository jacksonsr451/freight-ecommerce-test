from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from freight_ecommerce.config import Settings


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["freight-ecommerce-test"] = "freight-ecommerce-test"


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="Freight Ecommerce Test - Local API",
        version="0.1.0",
        description="Local bootstrap. Purchases and payments will be simulated.",
    )
    app.state.settings = settings if settings is not None else Settings()

    @app.get("/api/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        """Process liveness only; does not test PostgreSQL or external services."""
        return HealthResponse()

    return app
