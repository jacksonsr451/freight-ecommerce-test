from collections.abc import Iterator
from secrets import compare_digest
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from freight_ecommerce.catalog import service
from freight_ecommerce.catalog.schemas import (
    AdminProductPage,
    AdminProductView,
    ErrorResponse,
    ProductCreate,
    ProductPage,
    ProductPatch,
    ProductView,
    StockCheckRequest,
    StockCheckResponse,
)

admin_header = APIKeyHeader(name="X-Local-Admin-Key", scheme_name="LocalAdminKey", auto_error=False)


def require_local_admin(
    request: Request, key: Annotated[str | None, Security(admin_header)]
) -> None:
    settings = request.app.state.settings
    expected = settings.local_admin_key.get_secret_value()
    if settings.environment == "production" or not expected:
        service.fail(403, "local_admin_disabled", "Administração local desabilitada.")
    if key is None or not compare_digest(key.encode("utf-8"), expected.encode("utf-8")):
        service.fail(401, "admin_unauthorized", "Credencial administrativa local inválida.")


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine, expire_on_commit=False) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
PageNumber = Annotated[int, Query(ge=1, le=1_000_000)]
PageSize = Annotated[int, Query(ge=1, le=100)]

public = APIRouter(prefix="/api/products", tags=["catalog"])
admin = APIRouter(
    prefix="/api/admin/products",
    tags=["local-admin"],
    dependencies=[Depends(require_local_admin)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
errors = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


@public.get("", response_model=ProductPage, responses={503: {"model": ErrorResponse}})
def catalog(session: SessionDep, page: PageNumber = 1, page_size: PageSize = 20):
    """Only active products; price, measures and stock are read from the server database."""
    return service.list_products(session, page, page_size)


@public.get("/{product_id}", response_model=ProductView, responses=errors)
def detail(product_id: UUID, session: SessionDep):
    return service.view(*service.find_product(session, product_id))


@public.post("/{product_id}/stock-check", response_model=StockCheckResponse, responses=errors)
def stock_check(product_id: UUID, data: StockCheckRequest, session: SessionDep):
    """Read-only validation, not a reservation.

    Commercial fields cannot be supplied by the client.
    """
    return service.check_stock(session, product_id, data)


@admin.get("", response_model=AdminProductPage, responses=errors)
def admin_catalog(session: SessionDep, page: PageNumber = 1, page_size: PageSize = 20):
    return service.list_products(session, page, page_size, admin=True)


@admin.get("/{product_id}", response_model=AdminProductView, responses=errors)
def admin_detail(product_id: UUID, session: SessionDep):
    return service.view(*service.find_product(session, product_id, admin=True), admin=True)


@admin.post("", response_model=AdminProductView, status_code=201, responses=errors)
def create(data: ProductCreate, session: SessionDep):
    return service.create_product(session, data)


@admin.patch("/{product_id}", response_model=AdminProductView, responses=errors)
def patch(product_id: UUID, data: ProductPatch, session: SessionDep):
    return service.update_product(session, product_id, data)


@admin.delete("/{product_id}", status_code=204, responses=errors)
def delete(product_id: UUID, session: SessionDep) -> Response:
    """Logical deletion: preserve product identity and historical order references."""
    service.deactivate_product(session, product_id)
    return Response(status_code=204)
