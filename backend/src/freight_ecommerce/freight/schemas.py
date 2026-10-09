import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

PostalCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{8}$", min_length=8, max_length=8)]
Dimension = Annotated[int, Field(strict=True, ge=1, le=300)]
VolumeCount = Annotated[int, Field(strict=True, ge=1, le=1000)]


class Volume(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    weight_grams: Annotated[int, Field(strict=True, ge=1, le=50_000_000)]
    length_cm: Dimension
    width_cm: Dimension
    height_cm: Dimension


class QuoteRequest(BaseModel):
    """Contract L54–L73. Backend-only criteria; no arbitrary tenant selectors."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    request_key: UUID
    freight_company_id: UUID | None = None
    freight_location_id: UUID | None = None
    origin_postal_code: PostalCode | None = None
    destination_postal_code: PostalCode
    weight_kg: str
    declared_value_cents: Annotated[int, Field(strict=True, ge=0, le=100_000_000)]
    length_cm: Dimension | None = None
    width_cm: Dimension | None = None
    height_cm: Dimension | None = None
    volume_count: VolumeCount | None = None
    volumes: Annotated[tuple[Volume, ...], Field(min_length=1, max_length=1000)] | None = None
    service: Annotated[str, StringConstraints(max_length=80)] | None = None
    modal: Literal["rodoviario", "aereo", "maritimo", "ferroviario"] | None = None
    distance_meters: Annotated[int, Field(strict=True, ge=1, le=10_000_000)] | None = None
    invoice_count: Annotated[int, Field(strict=True, ge=0, le=1000)] | None = None

    @field_validator("origin_postal_code", "destination_postal_code", mode="before")
    @classmethod
    def canonical_postal_code(cls, value):
        if isinstance(value, str):
            return re.sub(r"[^0-9]", "", value)
        return value

    @field_validator("weight_kg", mode="before")
    @classmethod
    def canonical_weight(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,5}(?:[.,][0-9]{1,3})?", value):
            raise ValueError("Weight must be a decimal kg string with at most three decimal places")
        weight = Decimal(value.replace(",", "."))
        if not 0 < weight <= 50_000:
            raise ValueError("Weight must be positive and at most 50000 kg")
        return format(weight, ".3f")

    @model_validator(mode="after")
    def validate_dimensions_and_volumes(self):
        dimensions = (self.length_cm, self.width_cm, self.height_cm)
        if any(value is not None for value in dimensions):
            if any(value is None for value in dimensions) or self.volume_count is None:
                raise ValueError("All three dimensions and volume_count are required together")
        if self.volumes is not None:
            if len(self.volumes) != (self.volume_count if self.volume_count is not None else 1):
                raise ValueError("Individual volume count differs from volume_count")
            if (
                sum(volume.weight_grams for volume in self.volumes)
                != Decimal(self.weight_kg) * 1000
            ):
                raise ValueError("Individual volume weights differ from weight_kg")
        return self

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json", exclude_none=True),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")


@dataclass(frozen=True)
class PreparedQuote:
    request_key: UUID
    payload: bytes = field(repr=False)
    criteria_fingerprint: str


class ExternalModel(BaseModel):
    model_config = ConfigDict(extra="allow", hide_input_in_errors=True)
    __pydantic_extra__: dict[str, JsonValue] = Field(init=False)


class QuoteOption(ExternalModel):
    price_cents: Annotated[int, Field(strict=True, ge=0)]
    deadline_days: Annotated[int, Field(strict=True, ge=0)] | None = None
    carrier_name: str | None = None
    private_carrier_id: JsonValue = None
    rate_table_id: UUID | None = None
    matrix_version: JsonValue = None
    freight_company_id: UUID | None = None
    freight_location_id: UUID | None = None
    manual_only: Annotated[bool, Field(strict=True)] | None = None
    demonstration_only: Annotated[bool, Field(strict=True)] | None = None
    price_source: str | None = None
    carrier_workspace_id: UUID | None = None
    assumptions: JsonValue = None
    charged_weight_grams: Annotated[int, Field(strict=True)] | None = None
    cubage: JsonValue = None
    price_components: JsonValue = None
    calculation_snapshot: JsonValue = None
    calculated_at: JsonValue = None
    agreement_id: JsonValue = None
    subscription_id: JsonValue = None
    benefit_id: JsonValue = None


class QuoteSelection(ExternalModel):
    price_snapshot_id: JsonValue = None
    carrier_workspace_id: UUID | None = None
    rate_table_id: UUID | None = None
    price_cents: Annotated[int, Field(strict=True, ge=0)] | None = None


class QuoteData(ExternalModel):
    id: UUID
    status: Annotated[str, StringConstraints(min_length=1)]  # historical states remain open
    criteria: dict[str, JsonValue]
    options: list[QuoteOption]
    selection: QuoteSelection | None = None
    shipment_code: str | None = None
    created_at: datetime | None = None

    @field_validator("created_at", mode="before")
    @classmethod
    def iso_timestamp_or_null(cls, value):
        if value is not None and not isinstance(value, (str, datetime)):
            raise ValueError("created_at must be ISO 8601 or null")
        return value

    @model_validator(mode="after")
    def quoted_requires_options(self):
        if "request_key" in self.criteria:
            raise ValueError("Response criteria must not contain request_key")
        if self.status == "quoted" and not self.options:
            raise ValueError("Quoted without snapshots contradicts the documented action")
        return self


class QuoteEnvelope(ExternalModel):
    data: QuoteData = Field(repr=False)
