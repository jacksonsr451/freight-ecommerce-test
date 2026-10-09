from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from freight_ecommerce.cart.schemas import Revision


class QuoteCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: Revision
    packing_mode: Literal["equal_volumes", "weight_only"] = "equal_volumes"
    refresh: Annotated[bool, Field(strict=True)] = False


class SelectOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: Revision
    option_reference: UUID


class PublicOption(BaseModel):
    reference: UUID
    carrier_name: str | None
    price_cents: int
    deadline_days: int | None
    manual_only: bool | None
    demonstration_only: bool | None
    weight_only: bool
    manual_review_required: bool


class QuoteView(BaseModel):
    quote_reference: UUID
    cart_revision: int
    status: Literal["pending", "quoted", "unavailable", "fiscal_review", "failed", "invalidated"]
    mode: Literal["mock", "real"]
    weight_only: bool
    options: list[PublicOption]
    selected_option_reference: UUID | None
