from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from freight_ecommerce.catalog.schemas import Quantity

Revision = Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]


class CartCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AddItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: Revision
    product_id: UUID
    quantity: Quantity


class ChangeQuantity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: Revision
    quantity: Quantity


class DeliveryAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    postal_code: Annotated[
        str, StringConstraints(pattern=r"^[0-9]{8}$", min_length=8, max_length=8)
    ]
    street: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=255)]
    number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
    complement: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = (
        None
    )
    district: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    city: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    state: Annotated[str, StringConstraints(to_upper=True, pattern=r"^[A-Za-z]{2}$")]
    country: Literal["BR"] = "BR"


class ChangeAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: Revision
    address: DeliveryAddress | None  # explicit null clears the guest destination


class CartItemView(BaseModel):
    id: UUID
    product_id: UUID
    sku: str
    name: str
    quantity: int
    unit_price_cents: int
    line_total_cents: int
    weight_grams: int
    line_weight_grams: int
    length_cm: int
    width_cm: int
    height_cm: int
    available_quantity: int
    problem: Literal["inactive_product", "inventory_unavailable", "insufficient_stock"] | None


class CartView(BaseModel):
    id: UUID
    status: Literal["active", "checkout_pending", "checked_out", "abandoned"]
    revision: int
    delivery_address: DeliveryAddress | None
    items: list[CartItemView]
    subtotal_cents: int
    total_weight_grams: int
    total_quantity: int
    editable: bool
    checkout_ready: bool
    has_current_quote: bool
