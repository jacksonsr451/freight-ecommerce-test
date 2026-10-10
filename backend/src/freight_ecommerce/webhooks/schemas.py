from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

WebhookEventType = Literal[
    "shipment.created",
    "shipment.dispatch_updated",
    "shipment.tracking_updated",
    "shipment.labels_updated",
    "webhook.test",
]


class WebhookData(BaseModel):
    model_config = ConfigDict(extra="allow")

    shipment_id: str | None = Field(alias="shipmentId")
    public_code: str | None = Field(alias="publicCode")
    dispatch_status: str | None = Field(alias="dispatchStatus")


class PacksenviosWebhookEvent(BaseModel):
    """Versioned minimum documented webhook envelope; extra provider data is preserved."""

    model_config = ConfigDict(extra="allow")

    version: Literal[1]
    id: Annotated[str, Field(min_length=1)]
    type: WebhookEventType
    occurred_at: datetime = Field(alias="occurredAt")
    company_id: UUID = Field(alias="companyId")
    location_id: UUID | None = Field(alias="locationId")
    data: WebhookData

    @field_validator("occurred_at", mode="before")
    @classmethod
    def occurred_at_is_iso_text(cls, value):
        if not isinstance(value, str):
            raise ValueError("occurredAt must be an ISO 8601 string")
        return value

    @field_validator("occurred_at")
    @classmethod
    def timestamp_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurredAt must include an explicit timezone")
        return value


class WebhookReceiptAck(BaseModel):
    status: Literal["accepted", "duplicate"]
    event_id: str
    reconciliation_status: Literal["reconciliation_pending"]
    worker_status: Literal["not_configured", "notified", "unavailable"]
    out_of_order: bool


class WebhookReceiptView(BaseModel):
    id: UUID
    event_id: str
    event_type: WebhookEventType
    occurred_at: datetime
    received_at: datetime
    company_id: UUID
    location_id: UUID | None
    shipment_id: str | None
    public_code: str | None
    dispatch_status: str | None
    out_of_order: bool
    reconciliation_status: str
    worker_status: str
    body_sha256: str
    payload: dict[str, JsonValue]


class WebhookReceiptPage(BaseModel):
    items: list[WebhookReceiptView]
    total: int
