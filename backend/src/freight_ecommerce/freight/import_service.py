import hashlib
import json
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from freight_ecommerce.domain.models import IntegrationAudit, ShipmentImportBatch
from freight_ecommerce.domain.states import ImportStatus
from freight_ecommerce.freight.client import PacksenviosClient
from freight_ecommerce.freight.errors import FreightError
from freight_ecommerce.freight.import_validation import ValidatedImportFile
from freight_ecommerce.freight.imports import (
    ExportReadiness,
    ImportAvailability,
    ImportBatchPage,
    ImportDetail,
    ImportLocalBatch,
    ImportLocalPage,
    ImportSummary,
)


def availability(client: PacksenviosClient) -> ImportAvailability:
    real = client.settings.mode == "real"
    return ImportAvailability(
        mode=client.settings.mode,
        upload_enabled=real and client.settings.company_id is not None,
        company_configured=client.settings.company_id is not None,
        location_configured=client.settings.location_id is not None,
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


def _find_batch(session: Session, client: PacksenviosClient, batch_id: UUID) -> ShipmentImportBatch:
    batch = session.scalar(
        select(ShipmentImportBatch).where(
            ShipmentImportBatch.integration_scope == client.integration_scope,
            ShipmentImportBatch.external_batch_id == batch_id,
        )
    )
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
    )


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
