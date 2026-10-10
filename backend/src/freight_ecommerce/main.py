import asyncio
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError

from freight_ecommerce.cart.router import router as cart_router
from freight_ecommerce.catalog import router
from freight_ecommerce.config import Settings
from freight_ecommerce.database import build_engine
from freight_ecommerce.freight.client import PacksenviosClient
from freight_ecommerce.freight.config import FreightSettings
from freight_ecommerce.orders.router import router as orders_router
from freight_ecommerce.quoting.router import router as quoting_router


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["freight-ecommerce-test"] = "freight-ecommerce-test"


class RuntimeResponse(BaseModel):
    freight_mode: Literal["mock", "real"]
    purchases_simulated: Literal[True] = True


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    freight_client: PacksenviosClient | None = None,
) -> FastAPI:
    settings = settings if settings is not None else Settings()
    owns_engine = engine is None
    engine = engine if engine is not None else build_engine(settings)  # No connection at startup.

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if freight_client is None and app.state.freight_client is not None:
                await app.state.freight_client.aclose()
            if owns_engine:
                app.state.engine.dispose()

    app = FastAPI(
        title="Freight Ecommerce Test - Local API",
        version="0.1.0",
        description="Local simulated ecommerce. Catalog values are authoritative on the server.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.freight_client = freight_client
    app.state.freight_client_lock = asyncio.Lock()

    @app.exception_handler(IntegrityError)
    @app.exception_handler(StaleDataError)
    async def constraint_conflict(request, error):
        return JSONResponse(
            status_code=409,
            content={
                "detail": {
                    "code": "cart_conflict"
                    if request.url.path.startswith("/api/carts")
                    else "catalog_conflict",
                    "message": "Conflito de cadastro ou atualização concorrente.",
                }
            },
        )

    @app.exception_handler(OperationalError)
    async def database_unavailable(request, error):
        return JSONResponse(
            status_code=503,
            content={
                "detail": {
                    "code": "database_unavailable",
                    "message": "Banco local indisponível.",
                }
            },
        )

    app.include_router(router.public)
    app.include_router(router.admin)
    app.include_router(cart_router)
    app.include_router(quoting_router)
    app.include_router(orders_router)

    @app.get("/api/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        """Process liveness only; does not test PostgreSQL or external services."""
        return HealthResponse()

    @app.get("/api/runtime", response_model=RuntimeResponse, tags=["runtime"])
    def runtime(response: Response) -> RuntimeResponse:
        """Public mode only, without creating an HTTP client or calling a provider/database."""
        response.headers["Cache-Control"] = "no-store"
        try:
            config = (
                app.state.freight_client.settings
                if app.state.freight_client is not None
                else FreightSettings()
            )
        except ValueError:
            raise HTTPException(
                503,
                detail={
                    "code": "runtime_unavailable",
                    "message": "Configuração pública de modo indisponível.",
                },
            ) from None
        return RuntimeResponse(freight_mode=config.mode)

    return app
