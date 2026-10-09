from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from freight_ecommerce.catalog.router import errors
from freight_ecommerce.catalog.schemas import ErrorResponse
from freight_ecommerce.freight.client import PacksenviosClient, build_freight_client
from freight_ecommerce.quoting import service
from freight_ecommerce.quoting.schemas import QuoteCommand, QuoteView, SelectOption


async def get_client(request: Request) -> PacksenviosClient:
    async with request.app.state.freight_client_lock:
        if request.app.state.freight_client is None:
            try:
                request.app.state.freight_client = build_freight_client()
            except ValueError:
                raise HTTPException(
                    503,
                    detail={
                        "code": "freight_configuration_error",
                        "message": "Configuração backend de frete inválida.",
                    },
                ) from None
    return request.app.state.freight_client


ClientDep = Annotated[PacksenviosClient, Depends(get_client)]
router = APIRouter(
    prefix="/api/carts/{cart_id}/freight-quotes",
    tags=["local-freight"],
    responses={
        **errors,
        **{status: {"model": ErrorResponse} for status in (401, 403, 429, 502, 504)},
    },
)


@router.post("", response_model=QuoteView, responses={202: {"model": QuoteView}})
async def quote(
    cart_id: UUID, command: QuoteCommand, request: Request, response: Response, client: ClientDep
):
    result = await service.quote_cart(request.app.state.engine, client, cart_id, command)
    if result.status == "pending":
        response.status_code = 202
    return result


@router.get("/{quote_reference}", response_model=QuoteView)
def get(cart_id: UUID, quote_reference: UUID, request: Request, client: ClientDep):
    """Read/revalidate persisted data, without refreshing the provider or exposing raw snapshots."""
    return service.get_quote(request.app.state.engine, client, cart_id, quote_reference)


@router.post("/{quote_reference}/selection", response_model=QuoteView)
def select(
    cart_id: UUID, quote_reference: UUID, command: SelectOption, request: Request, client: ClientDep
):
    return service.select_option(
        request.app.state.engine, client, cart_id, quote_reference, command
    )
