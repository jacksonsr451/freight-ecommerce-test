from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from freight_ecommerce.domain.states import FulfillmentStatus, OrderStatus, PaymentStatus

AdminFulfillmentStatus = Literal[
    "separando",
    "embalado",
    "pronto_para_importacao",
    "importacao_pendente",
    "expedido_simulado",
    "entregue_simulado",
]


class CreateOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]
    submission_key: UUID


class ConfirmPaymentSimulation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_cart_revision: Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]
    outcome: Literal["approved", "declined", "pending"]


class CancelOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_cart_revision: Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]


class OrderLineView(BaseModel):
    product_id: UUID
    sku: str
    name: str
    quantity: int
    unit_price_cents: int
    line_total_cents: int
    product_snapshot: dict


class PaymentView(BaseModel):
    id: UUID
    status: PaymentStatus
    amount_cents: int
    simulation: Literal[True]


class FulfillmentView(BaseModel):
    status: FulfillmentStatus
    tracking_source: Literal["simulated"] = "simulated"


class ShippingDestination(BaseModel):
    postal_code: str
    city: str
    state: str


class OrderView(BaseModel):
    id: UUID
    status: OrderStatus
    simulation: Literal[True]
    created_at: datetime
    cart_revision: int
    subtotal_cents: int
    freight_cents: int
    total_cents: int
    selected_option_reference: UUID
    freight_review_required: bool
    shipping_destination: ShippingDestination
    items: list[OrderLineView]
    payment: PaymentView
    fulfillment: FulfillmentView | None
    cancellation_reason: Literal["payment_declined", "operator_cancelled"] | None = None


class OrderList(BaseModel):
    items: list[OrderView]
    total: int


class AdminOrderList(BaseModel):
    items: list[OrderView]
    total: int


class AdminFulfillmentTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_status: FulfillmentStatus
    status: AdminFulfillmentStatus


class AdminTimelineEvent(BaseModel):
    id: UUID
    occurred_at: datetime
    source: Literal["local_store", "local_admin", "simulated", "packsenvios"]
    event_key: str
    title: str
    internal_status: str | None
    external_status: str | None
    snapshot: dict


class AdminOrderDetail(BaseModel):
    order: OrderView
    snapshots: dict
    internal_fulfillment_status: FulfillmentStatus | None
    external_status: str | None
    timeline: list[AdminTimelineEvent]
