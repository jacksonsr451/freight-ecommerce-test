from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from freight_ecommerce.cart import service
from freight_ecommerce.cart.schemas import (
    AddItem,
    CartCreate,
    CartView,
    ChangeAddress,
    ChangeQuantity,
    CheckoutDetails,
)
from freight_ecommerce.catalog.router import SessionDep, errors

router = APIRouter(prefix="/api/carts", tags=["local-cart"], responses=errors)


@router.post("", response_model=CartView, status_code=201)
def create(data: CartCreate, session: SessionDep):
    return service.create_cart(session)


@router.get("/{cart_id}", response_model=CartView)
def get(cart_id: UUID, session: SessionDep):
    """Refresh catalog-derived values; persist invalidation if commercial criteria changed."""
    return service.get_cart(session, cart_id)


@router.post("/{cart_id}/items", response_model=CartView)
def add(cart_id: UUID, data: AddItem, session: SessionDep):
    """Add units to a product, merging with its existing line if present."""
    return service.add_item(session, cart_id, data)


@router.patch("/{cart_id}/items/{item_id}", response_model=CartView)
def quantity(cart_id: UUID, item_id: UUID, data: ChangeQuantity, session: SessionDep):
    return service.change_quantity(session, cart_id, item_id, data)


@router.delete("/{cart_id}/items/{item_id}", response_model=CartView)
def remove(
    cart_id: UUID,
    item_id: UUID,
    session: SessionDep,
    expected_revision: Annotated[int, Query(ge=1, le=2_147_483_647)],
):
    return service.remove_item(session, cart_id, item_id, expected_revision)


@router.put("/{cart_id}/address", response_model=CartView)
def address(cart_id: UUID, data: ChangeAddress, session: SessionDep):
    return service.change_address(session, cart_id, data)


@router.put("/{cart_id}/checkout-details", response_model=CartView)
def checkout_details(cart_id: UUID, data: CheckoutDetails, session: SessionDep):
    """Local cart-bound buyer/address; not a customer identity claim or a freight payload."""
    return service.save_checkout_details(session, cart_id, data)
