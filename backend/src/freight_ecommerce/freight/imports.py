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


class ImportLocalPage(BaseModel):
    items: list[ImportLocalBatch]
    total: int


class ImportDetail(BaseModel):
    batch: ImportLocalBatch
    external_status: str
    issue: JsonValue
    dispatch: JsonValue
    items: list[dict[str, Any]]
    has_more: bool
    next_cursor: int | None


class ImportAvailability(BaseModel):
    mode: Literal["mock", "real"]
    upload_enabled: bool
    company_configured: bool
    location_configured: bool


class ExportReadiness(BaseModel):
    can_export: bool = False
    missing_fields: list[str]


class ConfirmImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_valid_rows: bool = Field(strict=True)
    operator_reviewed: bool = Field(strict=True)
