import hashlib
import json
import math
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from freight_ecommerce.domain.base import utcnow
from freight_ecommerce.domain.models import IntegrationAudit, ShipmentImportBatch
from freight_ecommerce.domain.states import ImportStatus
from freight_ecommerce.freight.client import PacksenviosClient
from freight_ecommerce.freight.errors import FreightError
from freight_ecommerce.freight.import_validation import ValidatedImportFile
from freight_ecommerce.freight.imports import (
    DispatchSnapshot,
    ExportReadiness,
    ImportActivityEvent,
    ImportAvailability,
    ImportBatchPage,
    ImportDetail,
    ImportDispatchView,
    ImportLocalBatch,
    ImportLocalPage,
    ImportSummary,
    ImportTrackingRefreshView,
    ImportTrackingView,
)


def availability(client: PacksenviosClient) -> ImportAvailability:
    real = client.settings.mode == "real"
    return ImportAvailability(
        mode=client.settings.mode,
        upload_enabled=real and client.settings.company_id is not None,
        company_configured=client.settings.company_id is not None,
        location_configured=client.settings.location_id is not None,
        dispatch_connection_configured=client.settings.dispatch_connection_id is not None,
    )


def export_readiness() -> ExportReadiness:
    # The reference gives semantic column order, but not the literal line-1 instruction or
    # line-2 header values. Existing local orders also lack fiscal/sender identifiers.
    return ExportReadiness(
        can_export=False,
        missing_fields=[
            "official_template_instruction_line_1_and_exact_28_headers_unavailable",
            "invoice_number_and_valid_nfe_access_key",
            "recipient_cpf_cnpj_and_phone_with_ddd",
            "sender_name_and_valid_cpf_cnpj",
            "portal_template_must_be_downloaded_and_filled_by_authorized_operator",
        ],
    )


def _local_view(batch: ShipmentImportBatch) -> ImportLocalBatch:
    return ImportLocalBatch(
        id=batch.external_batch_id,
        filename=batch.filename,
        local_status=batch.status.value,
        external_status=batch.external_status,
        total=batch.total,
        valid=batch.valid,
        invalid=batch.invalid,
        imported=batch.imported,
        duplicates=batch.duplicates,
        processed=batch.processed,
        created_at=batch.created_at,
        dispatch_request_id=batch.external_dispatch_request_id,
        dispatch_status=batch.external_dispatch_status,
    )


def list_batches(session: Session, client: PacksenviosClient) -> ImportLocalPage:
    statement = select(ShipmentImportBatch).where(
        ShipmentImportBatch.integration_scope == client.integration_scope,
        ShipmentImportBatch.external_batch_id.is_not(None),
    )
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    batches = session.scalars(
        statement.order_by(ShipmentImportBatch.created_at.desc(), ShipmentImportBatch.id).limit(100)
    ).all()
    return ImportLocalPage(items=[_local_view(batch) for batch in batches], total=total)


def _deduplication_key(client: PacksenviosClient, file: ValidatedImportFile) -> str:
    identity = {
        "scope": client.integration_scope,
        "creator_reference": client.creator_reference,
        "company": str(client.settings.company_id),
        "location": str(client.settings.location_id) if client.settings.location_id else None,
        "content_sha256": file.content_sha256,
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _audit(
    session: Session,
    *,
    client: PacksenviosClient,
    operation: str,
    outcome: str,
    details: dict,
    batch: ShipmentImportBatch | None = None,
    http_status: int | None = None,
) -> None:
    session.add(
        IntegrationAudit(
            correlation_id=uuid4(),
            import_batch_id=batch.id if batch else None,
            operation=operation,
            mode=client.settings.mode,
            outcome=outcome,
            http_status=http_status,
            details=details,
        )
    )


def _raise_gateway_error(error: FreightError) -> None:
    if error.code == "import_real_mode_required":
        raise HTTPException(409, detail={"code": error.code, "message": str(error)}) from None
    status = error.http_status or 502
    if status < 400 or status > 599:
        status = 502
    headers = {}
    if error.retry_after_seconds is not None:
        headers["Retry-After"] = str(max(0, int(error.retry_after_seconds)))
    raise HTTPException(
        status,
        detail={"code": error.code, "message": str(error)},
        headers=headers or None,
    ) from None


def _sync_local_status(batch: ShipmentImportBatch, external_status: str) -> None:
    batch.external_status = external_status
    current = batch.status
    desired = {
        "queued": ImportStatus.VALIDATING,
        "parsing": ImportStatus.VALIDATING,
        "review": ImportStatus.READY_FOR_CONFIRMATION,
        "confirming": ImportStatus.CONFIRMATION_PENDING,
        "imported": ImportStatus.IMPORTED,
        "failed": ImportStatus.FAILED,
    }.get(external_status)
    if desired is None or desired == current:
        return
    paths = {
        ImportStatus.UPLOAD_PENDING: {
            ImportStatus.VALIDATING: [ImportStatus.VALIDATING],
            ImportStatus.READY_FOR_CONFIRMATION: [
                ImportStatus.VALIDATING,
                ImportStatus.READY_FOR_CONFIRMATION,
            ],
            ImportStatus.CONFIRMATION_PENDING: [
                ImportStatus.VALIDATING,
                ImportStatus.READY_FOR_CONFIRMATION,
                ImportStatus.CONFIRMATION_PENDING,
            ],
            ImportStatus.IMPORTED: [
                ImportStatus.VALIDATING,
                ImportStatus.READY_FOR_CONFIRMATION,
                ImportStatus.CONFIRMATION_PENDING,
                ImportStatus.IMPORTED,
            ],
            ImportStatus.FAILED: [ImportStatus.FAILED],
        },
        ImportStatus.VALIDATING: {
            ImportStatus.READY_FOR_CONFIRMATION: [ImportStatus.READY_FOR_CONFIRMATION],
            ImportStatus.CONFIRMATION_PENDING: [
                ImportStatus.READY_FOR_CONFIRMATION,
                ImportStatus.CONFIRMATION_PENDING,
            ],
            ImportStatus.IMPORTED: [
                ImportStatus.READY_FOR_CONFIRMATION,
                ImportStatus.CONFIRMATION_PENDING,
                ImportStatus.IMPORTED,
            ],
            ImportStatus.FAILED: [ImportStatus.FAILED],
        },
        ImportStatus.READY_FOR_CONFIRMATION: {
            ImportStatus.CONFIRMATION_PENDING: [ImportStatus.CONFIRMATION_PENDING],
            ImportStatus.IMPORTED: [
                ImportStatus.CONFIRMATION_PENDING,
                ImportStatus.IMPORTED,
            ],
        },
        ImportStatus.CONFIRMATION_PENDING: {
            ImportStatus.IMPORTED: [ImportStatus.IMPORTED],
            ImportStatus.FAILED: [ImportStatus.FAILED],
        },
    }
    for step in paths.get(current, {}).get(desired, []):
        batch.transition(step)


def _sync_counts(batch: ShipmentImportBatch, data: ImportSummary | ImportBatchPage) -> None:
    for field in ("total", "valid", "invalid", "imported", "duplicates", "processed"):
        setattr(batch, field, getattr(data, field))
    _sync_local_status(batch, data.status)


async def upload(
    session: Session,
    client: PacksenviosClient,
    file: ValidatedImportFile,
) -> ImportLocalBatch:
    if client.settings.mode != "real" or client.settings.company_id is None:
        _raise_gateway_error(
            FreightError(
                "import_real_mode_required",
                "Importação exige modo real e empresa configurada no backend.",
                http_status=409,
            )
        )
    key = _deduplication_key(client, file)
    existing = session.scalar(
        select(ShipmentImportBatch).where(ShipmentImportBatch.deduplication_key == key)
    )
    if existing is not None:
        return _local_view(existing)
    session.commit()
    try:
        response = await client.upload_order_import(file.filename, file.content, file.content_type)
    except FreightError as error:
        _audit(
            session,
            client=client,
            operation="order_import_upload",
            outcome=(
                "uncertain"
                if error.http_status is None
                or (error.code == "import_invalid_response" and error.http_status == 202)
                else "failed"
            ),
            http_status=error.http_status,
            details={"file_sha256": file.content_sha256, "error_code": error.code},
        )
        session.commit()
        _raise_gateway_error(error)
    batch = ShipmentImportBatch(
        integration_scope=client.integration_scope,
        creator_reference=client.creator_reference,
        freight_company_id=client.settings.company_id,
        freight_location_id=client.settings.location_id,
        filename=file.filename,
        content_sha256=file.content_sha256,
        deduplication_key=key,
        external_batch_id=response.id,
        total=response.total,
        valid=response.valid,
        invalid=response.invalid,
        imported=response.imported,
        duplicates=response.duplicates,
        processed=response.processed,
    )
    batch.transition(ImportStatus.UPLOAD_PENDING)
    batch.external_status = response.status
    session.add(batch)
    try:
        with session.begin_nested():
            session.flush()
            _audit(
                session,
                client=client,
                operation="order_import_uploaded",
                outcome="succeeded",
                http_status=202,
                batch=batch,
                details={
                    "file_sha256": file.content_sha256,
                    "external_batch_id": str(response.id),
                    "shipment_count_preflight": (
                        file.shipment_count if file.filename.lower().endswith(".csv") else None
                    ),
                    "preflight_level": (
                        "csv_structural_and_fiscal"
                        if file.filename.lower().endswith(".csv")
                        else "xlsx_zip_container_only"
                    ),
                    "simulation": False,
                },
            )
            session.flush()
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(ShipmentImportBatch).where(ShipmentImportBatch.deduplication_key == key)
        )
        if existing is None:
            existing = session.scalar(
                select(ShipmentImportBatch).where(
                    ShipmentImportBatch.integration_scope == client.integration_scope,
                    ShipmentImportBatch.external_batch_id == response.id,
                )
            )
        if existing is None:
            raise
        return _local_view(existing)
    return _local_view(batch)


def _find_batch(
    session: Session, client: PacksenviosClient, batch_id: UUID, *, lock: bool = False
) -> ShipmentImportBatch:
    statement = select(ShipmentImportBatch).where(
        ShipmentImportBatch.integration_scope == client.integration_scope,
        ShipmentImportBatch.external_batch_id == batch_id,
    )
    if lock:
        statement = statement.with_for_update()
    batch = session.scalar(statement)
    if batch is None:
        raise HTTPException(
            404, detail={"code": "import_batch_not_found", "message": "Lote local não encontrado."}
        )
    if (
        batch.freight_company_id != client.settings.company_id
        or batch.freight_location_id != client.settings.location_id
    ):
        raise HTTPException(
            404, detail={"code": "import_batch_not_found", "message": "Lote local não encontrado."}
        )
    return batch


def _dispatch_snapshot(value) -> DispatchSnapshot | None:
    if not isinstance(value, dict):
        return None
    try:
        return DispatchSnapshot.model_validate(value)
    except ValueError:
        return None


def _store_dispatch_snapshot(batch: ShipmentImportBatch, snapshot: DispatchSnapshot | None) -> None:
    if snapshot is None or snapshot.id is None:
        return
    if snapshot.batchId is not None and snapshot.batchId != batch.external_batch_id:
        return
    batch.external_dispatch_request_id = snapshot.id
    if snapshot.status is not None:
        batch.external_dispatch_status = snapshot.status
    if batch.status == ImportStatus.IMPORTED:
        batch.transition(ImportStatus.DISPATCH_PENDING)


def _last_dispatch_audit(session: Session, batch: ShipmentImportBatch) -> IntegrationAudit | None:
    return session.scalar(
        select(IntegrationAudit)
        .where(
            IntegrationAudit.import_batch_id == batch.id,
            IntegrationAudit.operation == "order_import_dispatch",
        )
        .order_by(IntegrationAudit.created_at.desc(), IntegrationAudit.id.desc())
        .limit(1)
    )


def _dispatch_blocked(session: Session, batch: ShipmentImportBatch) -> tuple[bool, bool]:
    latest = _last_dispatch_audit(session, batch)
    attempted_without_resolution = bool(
        latest is not None and latest.outcome in {"started", "uncertain"}
    )
    unresolved = bool(latest is not None and latest.outcome == "uncertain")
    return bool(batch.external_dispatch_request_id or attempted_without_resolution), unresolved


def _activity(session: Session, batch: ShipmentImportBatch) -> list[ImportActivityEvent]:
    rows = session.scalars(
        select(IntegrationAudit)
        .where(IntegrationAudit.import_batch_id == batch.id)
        .order_by(IntegrationAudit.created_at, IntegrationAudit.id)
        .limit(500)
    ).all()
    return [
        ImportActivityEvent(
            id=row.id,
            occurred_at=row.created_at,
            operation=row.operation,
            outcome=row.outcome,
            http_status=row.http_status,
            details=row.details,
        )
        for row in rows
    ]


async def get_batch(
    session: Session,
    client: PacksenviosClient,
    batch_id: UUID,
    *,
    cursor: int,
    errors_only: bool,
) -> ImportDetail:
    batch = _find_batch(session, client, batch_id)
    try:
        response = await client.get_order_import(batch_id, cursor=cursor, errors_only=errors_only)
    except FreightError as error:
        _raise_gateway_error(error)
    _sync_counts(batch, response)
    _store_dispatch_snapshot(batch, _dispatch_snapshot(response.dispatch))
    _audit(
        session,
        client=client,
        operation="order_import_status_read",
        outcome="succeeded",
        http_status=200,
        batch=batch,
        details={"cursor": cursor, "errors_only": errors_only, "external_status": response.status},
    )
    session.commit()
    return ImportDetail(
        batch=_local_view(batch),
        external_status=response.status,
        issue=response.issue,
        dispatch=response.dispatch,
        items=response.items,
        has_more=response.hasMore,
        next_cursor=response.nextCursor,
        dispatch_retry_blocked=_dispatch_blocked(session, batch)[0],
        activity=_activity(session, batch),
    )


async def get_tracking(
    session: Session,
    client: PacksenviosClient,
    batch_id: UUID,
    row_number: int,
) -> ImportTrackingView:
    batch = _find_batch(session, client, batch_id)
    try:
        snapshot = await client.get_order_import_tracking(batch_id, row_number)
    except FreightError as error:
        _raise_gateway_error(error)
    captured_at = utcnow()
    _audit(
        session,
        client=client,
        operation="order_import_tracking_snapshot",
        outcome="succeeded",
        http_status=200,
        batch=batch,
        details={
            "row_number": row_number,
            "source": "packsenvios",
            "snapshot": snapshot.model_dump(mode="json", exclude_none=False),
        },
    )
    session.flush()
    event = session.scalar(
        select(IntegrationAudit)
        .where(
            IntegrationAudit.import_batch_id == batch.id,
            IntegrationAudit.operation == "order_import_tracking_snapshot",
            IntegrationAudit.details["row_number"].as_integer() == row_number,
        )
        .order_by(IntegrationAudit.created_at.desc(), IntegrationAudit.id.desc())
        .limit(1)
    )
    if event is not None:
        captured_at = event.created_at
    session.commit()
    return ImportTrackingView(
        batch_id=batch_id,
        row_number=row_number,
        source="packsenvios",
        snapshot=snapshot,
        captured_at=captured_at,
    )


async def refresh_tracking(
    session: Session,
    client: PacksenviosClient,
    batch_id: UUID,
    row_number: int,
) -> ImportTrackingRefreshView:
    batch = _find_batch(session, client, batch_id, lock=True)
    latest = session.scalar(
        select(IntegrationAudit)
        .where(
            IntegrationAudit.import_batch_id == batch.id,
            IntegrationAudit.operation == "order_import_tracking_refresh",
            IntegrationAudit.details["row_number"].as_integer() == row_number,
            IntegrationAudit.outcome.in_(["started", "succeeded", "uncertain"]),
        )
        .order_by(IntegrationAudit.created_at.desc(), IntegrationAudit.id.desc())
        .limit(1)
    )
    now = utcnow()
    if latest is not None:
        remaining = 60 - (now - latest.created_at).total_seconds()
        if remaining > 0:
            raise HTTPException(
                429,
                detail={
                    "code": "tracking_refresh_throttled",
                    "message": (
                        "Atualização recente; respeite a janela de 60 segundos do lote/linha."
                    ),
                },
                headers={"Retry-After": str(max(1, math.ceil(remaining)))},
            )
    attempt = IntegrationAudit(
        correlation_id=uuid4(),
        import_batch_id=batch.id,
        operation="order_import_tracking_refresh",
        mode=client.settings.mode,
        outcome="started",
        details={"row_number": row_number, "source": "packsenvios", "status": "request_started"},
    )
    session.add(attempt)
    session.commit()
    try:
        queued = await client.refresh_order_import_tracking(batch_id, row_number)
    except FreightError as error:
        attempt.outcome = (
            "uncertain"
            if error.http_status is None
            or (error.code == "import_invalid_response" and error.http_status == 202)
            else "failed"
        )
        attempt.http_status = error.http_status
        attempt.details = {
            "row_number": row_number,
            "source": "packsenvios",
            "error_code": error.code,
        }
        session.commit()
        _raise_gateway_error(error)
    attempt.outcome = "started"
    attempt.http_status = 202
    attempt.details = {
        "row_number": row_number,
        "source": "packsenvios",
        "status": queued.status,
        "dedupe_window_seconds": 60,
    }
    session.commit()
    return ImportTrackingRefreshView(
        batch_id=batch_id,
        row_number=row_number,
        source="packsenvios",
        status=queued.status,
    )


def _dispatch_view(
    session: Session,
    batch: ShipmentImportBatch,
    snapshot: DispatchSnapshot | None,
    *,
    reconciliation_required: bool = False,
    external_dispatch_exists: bool = False,
) -> ImportDispatchView:
    blocked, uncertain_unresolved = _dispatch_blocked(session, batch)
    blocked = blocked or external_dispatch_exists
    return ImportDispatchView(
        batch=_local_view(batch),
        dispatch=snapshot,
        dispatch_retry_blocked=blocked,
        reconciliation_required=(
            reconciliation_required
            or (uncertain_unresolved and (snapshot is None or (snapshot.uncertain or 0) > 0))
            or (external_dispatch_exists and snapshot is None)
        ),
    )


async def dispatch_batch(
    session: Session,
    client: PacksenviosClient,
    batch_id: UUID,
) -> ImportDispatchView:
    batch = _find_batch(session, client, batch_id, lock=True)
    connection_id = client.settings.dispatch_connection_id
    if connection_id is None:
        _audit(
            session,
            client=client,
            operation="order_import_dispatch_blocked",
            outcome="failed",
            batch=batch,
            details={"reason": "dispatch_connection_not_configured"},
        )
        session.commit()
        raise HTTPException(
            409,
            detail={
                "code": "dispatch_connection_not_configured",
                "message": "Configure no backend a conexão existente e homologada da empresa.",
            },
        )
    try:
        current = await client.get_order_import(batch_id, cursor=0, errors_only=False)
    except FreightError as error:
        _raise_gateway_error(error)
    _sync_counts(batch, current)
    snapshot = _dispatch_snapshot(current.dispatch)
    _store_dispatch_snapshot(batch, snapshot)
    if current.dispatch is not None:
        _audit(
            session,
            client=client,
            operation="order_import_dispatch_reconciled",
            outcome="succeeded" if snapshot and snapshot.id else "uncertain",
            batch=batch,
            http_status=200,
            details={
                "dispatch_request_id": snapshot.id if snapshot else None,
                "external_dispatch_status": snapshot.status if snapshot else None,
                "source": "packsenvios",
            },
        )
        session.commit()
        return _dispatch_view(
            session,
            batch,
            snapshot,
            reconciliation_required=snapshot is None or (snapshot.uncertain or 0) > 0,
            external_dispatch_exists=True,
        )
    blocked, _ = _dispatch_blocked(session, batch)
    if blocked:
        _audit(
            session,
            client=client,
            operation="order_import_dispatch_reconciliation_required",
            outcome="uncertain",
            batch=batch,
            http_status=200,
            details={"source": "packsenvios", "dispatch_snapshot_found": False},
        )
        session.commit()
        return _dispatch_view(session, batch, None, reconciliation_required=True)
    if (
        current.status != "imported"
        or current.total < 1
        or current.imported != current.total
        or current.invalid != 0
        or current.processed < current.total
    ):
        _audit(
            session,
            client=client,
            operation="order_import_dispatch_blocked",
            outcome="failed",
            batch=batch,
            http_status=200,
            details={
                "external_status": current.status,
                "total": current.total,
                "imported": current.imported,
                "invalid": current.invalid,
                "processed": current.processed,
            },
        )
        session.commit()
        raise HTTPException(
            409,
            detail={
                "code": "import_dispatch_not_ready",
                "message": (
                    "Despacho exige lote imported, integralmente importado e sem inconsistências."
                ),
            },
        )
    attempt = IntegrationAudit(
        correlation_id=uuid4(),
        import_batch_id=batch.id,
        operation="order_import_dispatch",
        mode=client.settings.mode,
        outcome="started",
        details={
            "connection_id": str(connection_id),
            "source": "operator_confirmed",
            "external_batch_id": str(batch_id),
        },
    )
    session.add(attempt)
    session.commit()
    try:
        result = await client.dispatch_order_import(batch_id, connection_id)
    except FreightError as error:
        attempt.outcome = (
            "uncertain"
            if error.http_status is None
            or (error.code == "import_invalid_response" and error.http_status == 202)
            else "failed"
        )
        attempt.http_status = error.http_status
        attempt.details = {
            **attempt.details,
            "error_code": error.code,
            "external_status": None,
        }
        if attempt.outcome == "uncertain" and batch.status == ImportStatus.IMPORTED:
            batch.transition(ImportStatus.DISPATCH_PENDING)
        session.commit()
        _raise_gateway_error(error)
    snapshot = DispatchSnapshot.model_validate(
        result.model_dump(mode="json", by_alias=True, exclude_none=True)
    )
    batch.external_dispatch_request_id = result.id
    batch.external_dispatch_status = result.status
    if batch.status == ImportStatus.IMPORTED:
        batch.transition(ImportStatus.DISPATCH_PENDING)
    attempt.outcome = "uncertain" if result.uncertain > 0 else "started"
    attempt.http_status = 202
    attempt.details = {
        **result.model_dump(mode="json", by_alias=True, exclude_none=True),
        "source": "packsenvios",
        "enqueued_is_not_acceptance": True,
    }
    session.commit()
    return _dispatch_view(session, batch, snapshot)


async def confirm_batch(
    session: Session,
    client: PacksenviosClient,
    batch_id: UUID,
) -> ImportLocalBatch:
    batch = _find_batch(session, client, batch_id)
    try:
        current = await client.get_order_import(batch_id, cursor=0, errors_only=False)
        _sync_counts(batch, current)
        if current.status not in {"review", "confirming", "imported"} or current.valid < 1:
            _audit(
                session,
                client=client,
                operation="order_import_confirm_blocked",
                outcome="failed",
                batch=batch,
                details={"external_status": current.status, "valid": current.valid},
            )
            session.commit()
            raise HTTPException(
                409,
                detail={
                    "code": "import_confirmation_not_ready",
                    "message": "Lote ainda não está validado para confirmação.",
                },
            )
        response = await client.confirm_order_import(batch_id)
    except FreightError as error:
        _audit(
            session,
            client=client,
            operation="order_import_confirm",
            outcome="uncertain" if error.http_status is None else "failed",
            http_status=error.http_status,
            batch=batch,
            details={"error_code": error.code},
        )
        session.commit()
        _raise_gateway_error(error)
    _sync_counts(batch, response)
    _audit(
        session,
        client=client,
        operation="order_import_confirm",
        outcome="succeeded",
        http_status=202,
        batch=batch,
        details={"external_status": response.status, "operator_confirmed": True},
    )
    session.commit()
    return _local_view(batch)
