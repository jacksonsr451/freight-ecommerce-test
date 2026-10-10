import re
from datetime import datetime
from time import perf_counter
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, JsonValue
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from freight_ecommerce.domain.base import utcnow
from freight_ecommerce.domain.models import (
    FreightQuote,
    IntegrationAudit,
    ShipmentImportBatch,
    WebhookReceipt,
)
from freight_ecommerce.domain.states import ImportStatus
from freight_ecommerce.freight.config import FreightSettings

router = APIRouter(tags=["safe-diagnostics"])
SAFE_DETAIL_FIELDS = {
    "packing_mode",
    "simulation",
    "current",
    "code",
    "error_code",
    "external_status",
    "status",
    "cursor",
    "errors_only",
    "row_number",
    "from_status",
    "to_status",
    "inventory_reserved",
    "stock_reservations_released",
    "operator_confirmed",
    "dispatch_snapshot_found",
    "valid",
    "invalid",
    "imported",
    "duplicates",
    "processed",
    "total",
    "enqueued",
    "accepted",
    "rejected",
    "uncertain",
    "source",
    "preflight_level",
    "shipment_count_preflight",
    "dedupe_window_seconds",
    "retry_after_seconds",
}
SAFE_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
SAFE_CONTRACT_STATUSES = {
    "quoted",
    "unavailable",
    "fiscal_review",
    "queued",
    "parsing",
    "review",
    "confirming",
    "imported",
    "failed",
}
SAFE_LOCAL_STATES = {
    "payment_pending",
    "paid_simulated",
    "payment_declined",
    "cancelled",
    "pago_simulado",
    "separando",
    "embalado",
    "pronto_para_importacao",
    "importacao_pendente",
    "expedido_simulado",
    "entregue_simulado",
    "cancelado",
    "request_started",
}


class DiagnosticCheck(BaseModel):
    name: str
    status: Literal["ok", "unavailable", "configured", "not_configured", "not_checked"]
    latency_ms: int | None = None
    details: dict[str, JsonValue]


class DiagnosticOperation(BaseModel):
    correlation_id: UUID
    operation: str
    mode: Literal["mock", "real"]
    outcome: Literal["started", "succeeded", "failed", "uncertain"]
    occurred_at: datetime
    http_status: int | None
    latency_ms: int | None
    request_key: UUID | None
    quote_id: UUID | None
    external_quote_id: UUID | None
    import_batch_id: UUID | None
    error_code: str | None
    retry_after_seconds: float | None
    redacted_details: dict[str, JsonValue]
    snapshot_summary: dict[str, JsonValue] | None


class DiagnosticReport(BaseModel):
    generated_at: datetime
    freight_mode: Literal["mock", "real"] | None
    purchases_simulated: Literal[True] = True
    checks: list[DiagnosticCheck]
    operations: list[DiagnosticOperation]
    pending_import_batches: int | None
    pending_webhook_receipts: int | None


def _safe_value(name: str, value: Any) -> JsonValue | None:
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, str) and len(value) <= 160:
        if name in {
            "code",
            "error_code",
            "external_status",
            "status",
            "source",
            "from_status",
            "to_status",
            "packing_mode",
            "preflight_level",
        }:
            if not SAFE_CODE.fullmatch(value):
                return "[redacted]"
            if name in {"external_status", "status"} and value not in SAFE_CONTRACT_STATUSES:
                return "[redacted]"
            if name in {"from_status", "to_status"} and value not in SAFE_LOCAL_STATES:
                return "[redacted]"
            return value
        return value
    return None


def _safe_audit_details(
    details: dict,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue] | None, str | None, int | None]:
    safe = {
        key: result
        for key, value in details.items()
        if key in SAFE_DETAIL_FIELDS
        if (result := _safe_value(key, value)) is not None
    }
    error_code = _safe_value("error_code", details.get("error_code", details.get("code")))
    retry = details.get("retry_after_seconds")
    retry_after = float(retry) if isinstance(retry, (int, float)) and 0 <= retry <= 86_400 else None
    snapshot = details.get("snapshot")
    snapshot_summary = None
    if isinstance(snapshot, dict):
        event_values = snapshot.get("events")
        label_values = snapshot.get("labels")
        snapshot_summary = {
            "redacted": True,
            "field_count": len(snapshot),
            "event_count": len(event_values) if isinstance(event_values, list) else None,
            "label_count": len(label_values) if isinstance(label_values, list) else None,
        }
    return safe, snapshot_summary, error_code if isinstance(error_code, str) else None, retry_after


def _mode(request: Request) -> tuple[Literal["mock", "real"] | None, DiagnosticCheck]:
    try:
        configured = (
            request.app.state.freight_client.settings
            if request.app.state.freight_client is not None
            else FreightSettings()
        )
    except ValueError:
        return None, DiagnosticCheck(
            name="freight_adapter",
            status="unavailable",
            details={"external_probe": "not_checked", "credentials_exposed": False},
        )
    mode = configured.mode
    ready = bool(
        mode == "mock"
        or (
            configured.base_url
            and configured.api_key.get_secret_value()
            and configured.company_id is not None
        )
    )
    return mode, DiagnosticCheck(
        name="freight_adapter",
        status="configured" if ready else "unavailable",
        details={
            "mode": mode,
            "company_configured": configured.company_id is not None,
            "location_configured": configured.location_id is not None,
            "dispatch_connection_configured": configured.dispatch_connection_id is not None,
            "external_probe": "not_checked",
            "credentials_exposed": False,
        },
    )


@router.get("/api/diagnostics", response_model=DiagnosticReport)
def diagnostics(request: Request, response: Response) -> DiagnosticReport:
    """Read-only support report: allowlisted fields only; never returns raw audit snapshots."""
    response.headers["Cache-Control"] = "no-store"
    mode, freight_check = _mode(request)
    checks = [
        DiagnosticCheck(name="api", status="ok", details={"process": "running"}),
        freight_check,
        DiagnosticCheck(
            name="external_api",
            status="not_checked",
            details={"reason": "diagnostic refresh never performs a provider request"},
        ),
        DiagnosticCheck(
            name="queues",
            status="not_configured",
            details={"worker_health": "not_observable"},
        ),
        DiagnosticCheck(
            name="webhook_receiver",
            status=(
                "configured"
                if request.app.state.settings.packsenvios_webhook_secret.get_secret_value()
                and request.app.state.settings.webhook_timestamp_format
                and request.app.state.settings.webhook_company_id
                else "not_configured"
            ),
            details={"homologated": False, "secret_exposed": False},
        ),
    ]
    database_latency = None
    operations: list[DiagnosticOperation] = []
    pending_import_batches = None
    pending_webhook_receipts = None
    database_started = perf_counter()
    engine = request.app.state.engine
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database_latency = max(0, int((perf_counter() - database_started) * 1000))
        with Session(engine) as session:
            rows = session.execute(
                select(IntegrationAudit, FreightQuote.external_quote_request_id)
                .outerjoin(FreightQuote, IntegrationAudit.quote_id == FreightQuote.id)
                .order_by(IntegrationAudit.created_at.desc(), IntegrationAudit.id.desc())
                .limit(50)
            ).all()
            for audit, external_quote_id in rows:
                safe, snapshot_summary, error_code, retry_after = _safe_audit_details(audit.details)
                operations.append(
                    DiagnosticOperation(
                        correlation_id=audit.correlation_id,
                        operation=audit.operation,
                        mode=audit.mode,
                        outcome=audit.outcome,
                        occurred_at=audit.created_at,
                        http_status=audit.http_status,
                        latency_ms=audit.latency_ms,
                        request_key=audit.request_key,
                        quote_id=audit.quote_id,
                        external_quote_id=external_quote_id,
                        import_batch_id=audit.import_batch_id,
                        error_code=error_code,
                        retry_after_seconds=retry_after,
                        redacted_details=safe,
                        snapshot_summary=snapshot_summary,
                    )
                )
            pending_import_batches = session.scalar(
                select(func.count())
                .select_from(ShipmentImportBatch)
                .where(
                    ShipmentImportBatch.status.in_(
                        [
                            ImportStatus.UPLOAD_PENDING,
                            ImportStatus.VALIDATING,
                            ImportStatus.READY_FOR_CONFIRMATION,
                            ImportStatus.CONFIRMATION_PENDING,
                            ImportStatus.DISPATCH_PENDING,
                        ]
                    )
                )
            )
            pending_webhook_receipts = session.scalar(
                select(func.count())
                .select_from(WebhookReceipt)
                .where(WebhookReceipt.reconciliation_status == "reconciliation_pending")
            )
    except SQLAlchemyError:
        checks.append(
            DiagnosticCheck(
                name="postgresql",
                status="unavailable",
                details={"error": "database_unavailable", "connection_details_exposed": False},
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                name="postgresql",
                status="ok",
                latency_ms=database_latency,
                details={"query": "SELECT 1", "connection_details_exposed": False},
            )
        )
    return DiagnosticReport(
        generated_at=utcnow(),
        freight_mode=mode,
        checks=checks,
        operations=operations,
        pending_import_batches=pending_import_batches,
        pending_webhook_receipts=pending_webhook_receipts,
    )
