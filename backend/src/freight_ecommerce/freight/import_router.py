from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile

from freight_ecommerce.catalog.router import SessionDep, errors, require_local_admin
from freight_ecommerce.freight.client import PacksenviosClient
from freight_ecommerce.freight.import_service import (
    availability,
    confirm_batch,
    export_readiness,
    get_batch,
    list_batches,
    upload,
)
from freight_ecommerce.freight.import_validation import ImportFileError, validate_import_file
from freight_ecommerce.freight.imports import (
    ConfirmImport,
    ExportReadiness,
    ImportAvailability,
    ImportDetail,
    ImportLocalBatch,
    ImportLocalPage,
)
from freight_ecommerce.quoting.router import get_client

ClientDep = Annotated[PacksenviosClient, Depends(get_client)]
Cursor = Annotated[int, Query(ge=0, le=1_048_576)]
router = APIRouter(
    prefix="/api/admin/imports",
    tags=["local-admin-imports"],
    dependencies=[Depends(require_local_admin)],
    responses={
        **errors,
        401: {"description": "Credencial administrativa local inválida."},
        403: {"description": "Administração local desabilitada."},
        429: {"description": "Quota da API externa; respeite Retry-After."},
        502: {"description": "Falha segura do gateway externo."},
    },
)


@router.get("/availability", response_model=ImportAvailability)
def get_availability(client: ClientDep):
    return availability(client)


@router.get("/export-readiness", response_model=ExportReadiness)
def get_export_readiness():
    return export_readiness()


@router.get("", response_model=ImportLocalPage)
def get_batches(session: SessionDep, client: ClientDep):
    return list_batches(session, client)


@router.post("", response_model=ImportLocalBatch, status_code=202)
async def upload_file(
    session: SessionDep,
    client: ClientDep,
    response: Response,
    file: Annotated[UploadFile, File()],
):
    content = await file.read(29_999_105)
    try:
        validated = validate_import_file(file.filename, file.content_type, content)
    except ImportFileError as error:
        detail = {"code": error.code, "message": str(error)}
        if error.row is not None:
            detail["row"] = error.row
        if error.field is not None:
            detail["field"] = error.field
        raise HTTPException(422, detail=detail) from None
    batch = await upload(session, client, validated)
    response.status_code = 202
    return batch


@router.get("/{batch_id}", response_model=ImportDetail)
async def batch_detail(
    batch_id: UUID,
    session: SessionDep,
    client: ClientDep,
    cursor: Cursor = 0,
    errors_only: bool = False,
):
    return await get_batch(session, client, batch_id, cursor=cursor, errors_only=errors_only)


@router.post("/{batch_id}/confirm", response_model=ImportLocalBatch, status_code=202)
async def confirm(
    batch_id: UUID,
    data: ConfirmImport,
    session: SessionDep,
    client: ClientDep,
    response: Response,
):
    if data.confirm_valid_rows is not True or data.operator_reviewed is not True:
        raise HTTPException(
            422,
            detail={
                "code": "operator_confirmation_required",
                "message": "Revise o lote e confirme explicitamente as linhas válidas.",
            },
        )
    result = await confirm_batch(session, client, batch_id)
    response.status_code = 202
    return result
