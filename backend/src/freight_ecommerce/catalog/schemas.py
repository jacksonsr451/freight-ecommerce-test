from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SKU = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
PriceInput = Annotated[int, Field(strict=True, ge=0, le=100_000_000)]
Weight = Annotated[int, Field(strict=True, ge=1, le=50_000_000)]
Dimension = Annotated[int, Field(strict=True, ge=1, le=300)]
Stock = Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)]
Quantity = Annotated[int, Field(strict=True, ge=1, le=1000)]
ProductStatus = Literal["active", "inactive"]


def patch_schema(schema):
    """Document the before-validator rules in the local OpenAPI contract too."""
    schema["minProperties"] = 1
    for property_ in schema.get("properties", {}).values():
        property_.pop("default", None)
        variants = property_.pop("anyOf", None)
        if variants:
            allowed = [variant for variant in variants if variant.get("type") != "null"]
            if len(allowed) == 1:
                property_.update(allowed[0])
            else:
                property_["anyOf"] = allowed


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: SKU
    name: Name
    price_cents: PriceInput
    weight_grams: Weight
    length_cm: Dimension
    width_cm: Dimension
    height_cm: Dimension
    stock_on_hand: Stock
    status: ProductStatus = "active"


class ProductPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=patch_schema)
    sku: SKU | None = None
    name: Name | None = None
    price_cents: PriceInput | None = None
    weight_grams: Weight | None = None
    length_cm: Dimension | None = None
    width_cm: Dimension | None = None
    height_cm: Dimension | None = None
    stock_on_hand: Stock | None = None
    status: ProductStatus | None = None

    @model_validator(mode="before")
    @classmethod
    def require_nonempty_nonnull_patch(cls, value):
        if isinstance(value, dict) and (not value or any(item is None for item in value.values())):
            raise ValueError("Patch must contain fields with non-null values")
        return value


class ProductView(BaseModel):
    id: UUID
    sku: str
    name: str
    price_cents: int = Field(ge=0)
    weight_grams: int = Field(ge=1)
    length_cm: int = Field(ge=1, le=300)
    width_cm: int = Field(ge=1, le=300)
    height_cm: int = Field(ge=1, le=300)
    stock_available: int = Field(ge=0)
    status: ProductStatus


class InventoryView(BaseModel):
    on_hand: int = Field(ge=0)
    reserved: int = Field(ge=0)
    available: int = Field(ge=0)
    version: int


class AdminProductView(ProductView):
    inventory: InventoryView
    created_at: datetime
    updated_at: datetime


class ProductPage(BaseModel):
    items: list[ProductView]
    total: int
    page: int
    page_size: int
    total_pages: int


class AdminProductPage(BaseModel):
    items: list[AdminProductView]
    total: int
    page: int
    page_size: int
    total_pages: int


class StockCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: Quantity


class StockCheckResponse(BaseModel):
    product_id: UUID
    requested_quantity: int
    available_quantity: int
    unit_price_cents: int
    subtotal_cents: int
    total_weight_grams: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    available_quantity: int | None = None


class ErrorResponse(BaseModel):
    detail: ErrorDetail
