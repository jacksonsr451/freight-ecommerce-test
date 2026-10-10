from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from freight_ecommerce.catalog.router import SessionDep, require_local_admin
from freight_ecommerce.webhooks.schemas import WebhookReceiptAck, WebhookReceiptPage
from freight_ecommerce.webhooks.service import (
    MAX_WEBHOOK_BODY_BYTES,
    list_pending_receipts,
    notify_reconciliation,
    persist_receipt,
    receipt_ack,
    verify_webhook,
)

receiver = APIRouter(
    prefix="/api/webhooks/packsenvios",
    tags=["webhook-receiver-local-unhomologated"],
)
admin = APIRouter(
    prefix="/api/admin/webhooks",
    tags=["local-admin-webhooks"],
    dependencies=[Depends(require_local_admin)],
)
Page = Annotated[int, Query(ge=1, le=1_000_000)]
PageSize = Annotated[int, Query(ge=1, le=100)]


async def capture_raw_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None and declared.isascii() and declared.isdigit():
        if int(declared) > MAX_WEBHOOK_BODY_BYTES:
            from fastapi import HTTPException

            raise HTTPException(
                413,
                detail={
                    "code": "webhook_body_too_large",
                    "message": "Corpo excede o limite local do receptor.",
                },
            )
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_WEBHOOK_BODY_BYTES:
            from fastapi import HTTPException

            raise HTTPException(
                413,
                detail={
                    "code": "webhook_body_too_large",
                    "message": "Corpo excede o limite local do receptor.",
                },
            )
        body.extend(chunk)
    return bytes(body)


@receiver.post(
    "",
    response_model=WebhookReceiptAck,
    status_code=202,
    responses={200: {"model": WebhookReceiptAck}},
    summary="Non-homologated local webhook receiver",
)
async def accept_packsenvios_webhook(request: Request, session: SessionDep, response: Response):
    """Receive exact signed bytes, durably dedupe, then acknowledge a pending signal."""
    raw_body = await capture_raw_body(request)
    event = verify_webhook(
        request.app.state.settings,
        raw_body=raw_body,
        content_type=request.headers.get("content-type"),
        timestamp_header=request.headers.get("X-Packsenvios-Timestamp"),
        signature_header=request.headers.get("X-Packsenvios-Signature"),
        delivery_header=request.headers.get("X-Packsenvios-Delivery"),
    )
    receipt, duplicate = persist_receipt(
        session,
        event,
        raw_body,
        request.headers.get("X-Packsenvios-Delivery"),
    )
    if duplicate:
        response.status_code = 200
        return receipt_ack(receipt, duplicate=True)
    await notify_reconciliation(request.app, session, receipt)
    response.status_code = 202
    return receipt_ack(receipt, duplicate=False)


@admin.get("/receipts", response_model=WebhookReceiptPage)
def pending_receipts(session: SessionDep, page: Page = 1, page_size: PageSize = 50):
    """List local webhook signals awaiting reconciliation; infer no external status."""
    return list_pending_receipts(session, page, page_size)
