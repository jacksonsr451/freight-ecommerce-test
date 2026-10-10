from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from freight_ecommerce.catalog.router import SessionDep, errors
from freight_ecommerce.freight.client import PacksenviosClient
from freight_ecommerce.orders import service
from freight_ecommerce.orders.schemas import (
    CancelOrder,
    ConfirmPaymentSimulation,
    CreateOrder,
    OrderList,
    OrderView,
)
from freight_ecommerce.quoting.router import get_client

ClientDep = Annotated[PacksenviosClient, Depends(get_client)]
router = APIRouter(prefix="/api", tags=["local-orders"], responses=errors)
Page = Annotated[int, Query(ge=1, le=1_000_000)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.post(
    "/carts/{cart_id}/orders", response_model=OrderView, responses={200: {"model": OrderView}}
)
def create(
    cart_id: UUID, data: CreateOrder, session: SessionDep, client: ClientDep, response: Response
):
    result, created = service.create(session, client, cart_id, data)
    response.status_code = 201 if created else 200
    return result


@router.post("/orders/{order_id}/confirm", response_model=OrderView)
def confirm(order_id: UUID, data: ConfirmPaymentSimulation, session: SessionDep):
    """Local payment simulation only; no financial provider or Packsenvios call."""
    result, _ = service.confirm(session, order_id, data)
    return result


@router.post("/orders/{order_id}/cancel", response_model=OrderView)
def cancel(order_id: UUID, data: CancelOrder, session: SessionDep):
    """Compensate active local reservations only before fulfillment starts."""
    result, _ = service.cancel(session, order_id, data)
    return result


@router.get("/orders/{order_id}", response_model=OrderView)
def detail(order_id: UUID, session: SessionDep):
    return service.get_order(session, order_id)


@router.get("/carts/{cart_id}/orders", response_model=OrderList)
def history(cart_id: UUID, session: SessionDep, page: Page = 1, page_size: PageSize = 20):
    return service.list_orders(session, cart_id, page, page_size)
