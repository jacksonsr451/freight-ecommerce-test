from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class ImportSummary(BaseModel):
    """Documented upload/confirm summary; unknown fields remain opaque and are not persisted."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: UUID
    filename: str = Field(max_length=255)
    status: str = Field(min_length=1, max_length=80)
    total: int = Field(ge=0)
    valid: int = Field(ge=0)
    invalid: int = Field(ge=0)
    imported: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    processed: int = Field(ge=0)
    issue: JsonValue = None
    created_at: JsonValue = Field(alias="createdAt", default=None)
    can_delete: bool = Field(alias="canDelete")
    tms_available: bool = Field(alias="tmsAvailable")
    dispatch: JsonValue = None


class ImportBatchPage(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: UUID
    filename: str = Field(max_length=255)
    status: str = Field(min_length=1, max_length=80)
    total: int = Field(ge=0)
    valid: int = Field(ge=0)
    invalid: int = Field(ge=0)
    imported: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    processed: int = Field(ge=0)
    issue: JsonValue = None
    canDelete: bool = False
    tmsAvailable: bool = False
    dispatch: JsonValue = None
    items: list[dict[str, Any]]
    hasMore: bool
    nextCursor: int | None = Field(default=None, ge=0, le=1_048_576)

    @field_validator("items", mode="before")
    @classmethod
    def validate_rows(cls, value):
        if not isinstance(value, list) or len(value) > 50:
            raise ValueError("Import response exceeds the documented 50 rows per page")
        for row in value:
            if not isinstance(row, dict) or "row" not in row or "status" not in row:
                raise ValueError("Import row does not match the documented response shape")
        return value


class DispatchResult(BaseModel):
    """Fields documented for the 202 dispatch response; unknown status values stay open."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=160)
    batchId: UUID
    connectionId: UUID
    status: str = Field(min_length=1, max_length=80)
    total: int = Field(ge=0)
    enqueued: int = Field(ge=0)
    accepted: int = Field(ge=0)
    rejected: int = Field(ge=0)
    uncertain: int = Field(ge=0)
    issue: JsonValue = None


class DispatchSnapshot(BaseModel):
    """Partial dispatch projection for reconciliation; never use it to infer delivery."""

    model_config = ConfigDict(extra="allow")

    id: str | None = Field(default=None, max_length=160)
    batchId: UUID | None = None
    connectionId: UUID | None = None
    status: str | None = Field(default=None, max_length=80)
    total: int | None = Field(default=None, ge=0)
    enqueued: int | None = Field(default=None, ge=0)
    accepted: int | None = Field(default=None, ge=0)
    rejected: int | None = Field(default=None, ge=0)
    uncertain: int | None = Field(default=None, ge=0)
    issue: JsonValue = None


class TrackingSnapshot(BaseModel):
    """Documented top-level snapshot fields; event and label payloads remain opaque JSON."""

    model_config = ConfigDict(extra="allow")

    code: JsonValue = None
    reference: JsonValue = None
    acceptedAt: JsonValue = None
    updatedAt: JsonValue = None
    issue: JsonValue = None
    labels: JsonValue = None
    labelsAt: JsonValue = None
    events: JsonValue = None


class TrackingRefreshQueued(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["queued"]


class ImportLocalBatch(BaseModel):
    id: UUID
    filename: str
    local_status: str
    external_status: str | None
    total: int
    valid: int
    invalid: int
    imported: int
    duplicates: int
    processed: int
    created_at: datetime
    dispatch_request_id: str | None = None
    dispatch_status: str | None = None


class ImportLocalPage(BaseModel):
    items: list[ImportLocalBatch]
    total: int


class ImportActivityEvent(BaseModel):
    id: UUID
    occurred_at: datetime
    operation: str
    outcome: str
    http_status: int | None
    details: dict


class ImportDetail(BaseModel):
    batch: ImportLocalBatch
    external_status: str
    issue: JsonValue
    dispatch: JsonValue
    items: list[dict[str, Any]]
    has_more: bool
    next_cursor: int | None
    dispatch_retry_blocked: bool = False
    activity: list[ImportActivityEvent] = Field(default_factory=list)


class ImportDispatchView(BaseModel):
    batch: ImportLocalBatch
    dispatch: DispatchSnapshot | None
    dispatch_retry_blocked: bool
    reconciliation_required: bool


class ImportTrackingView(BaseModel):
    batch_id: UUID
    row_number: int
    source: Literal["packsenvios"]
    snapshot: TrackingSnapshot
    captured_at: datetime
    refresh_queued: bool = False


class ImportTrackingRefreshView(BaseModel):
    batch_id: UUID
    row_number: int
    source: Literal["packsenvios"]
    status: Literal["queued"]


class ConfirmDispatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_dispatch: bool = Field(strict=True)
    operator_confirmed: bool = Field(strict=True)


class ImportAvailability(BaseModel):
    mode: Literal["mock", "real"]
    upload_enabled: bool
    company_configured: bool
    location_configured: bool
    dispatch_connection_configured: bool


class ExportReadiness(BaseModel):
    can_export: bool = False
    missing_fields: list[str]


class ConfirmImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_valid_rows: bool = Field(strict=True)
    operator_reviewed: bool = Field(strict=True)
