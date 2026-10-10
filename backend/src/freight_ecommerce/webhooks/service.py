import hashlib
import hmac
import inspect
import logging
import re
from datetime import UTC, datetime

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from freight_ecommerce.config import Settings
from freight_ecommerce.domain.models import WebhookReceipt
from freight_ecommerce.webhooks.schemas import (
    PacksenviosWebhookEvent,
    WebhookReceiptAck,
    WebhookReceiptPage,
    WebhookReceiptView,
)

logger = logging.getLogger(__name__)
MAX_WEBHOOK_BODY_BYTES = 1_048_576  # Local receiver resource cap; not a provider limit.
RECOMMENDED_TIMESTAMP_WINDOW_SECONDS = 300


def _receiver_configuration(settings: Settings) -> str:
    secret = settings.packsenvios_webhook_secret.get_secret_value()
    if (
        not secret
        or settings.webhook_timestamp_format is None
        or settings.webhook_company_id is None
    ):
        raise HTTPException(
            503,
            detail={
                "code": "webhook_receiver_not_configured",
                "message": "Receptor não configurado para contexto autorizado.",
            },
        )
    return secret


def verify_webhook(
    settings: Settings,
    *,
    raw_body: bytes,
    content_type: str | None,
    timestamp_header: str | None,
    signature_header: str | None,
    delivery_header: str | None,
    now: datetime | None = None,
) -> PacksenviosWebhookEvent:
    secret = _receiver_configuration(settings)
    if len(raw_body) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(
            413,
            detail={
                "code": "webhook_body_too_large",
                "message": "Corpo excede o limite local do receptor.",
            },
        )
    if (content_type or "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(
            415,
            detail={
                "code": "webhook_content_type_invalid",
                "message": "Esperado application/json.",
            },
        )
    if (
        timestamp_header is None
        or signature_header is None
        or not re.fullmatch(r"[0-9]{1,12}", timestamp_header)
        or not re.fullmatch(r"v1=[0-9a-fA-F]{64}", signature_header)
    ):
        raise HTTPException(
            401,
            detail={"code": "webhook_unauthorized", "message": "Assinatura de webhook inválida."},
        )
    if settings.webhook_timestamp_format != "unix_seconds":
        raise HTTPException(
            503,
            detail={
                "code": "webhook_timestamp_format_unverified",
                "message": "Formato do timestamp ainda não foi confirmado no contrato do provedor.",
            },
        )
    timestamp_value = int(timestamp_header)
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Webhook verifier clock must be timezone aware")
    if abs(current.timestamp() - timestamp_value) > RECOMMENDED_TIMESTAMP_WINDOW_SECONDS:
        raise HTTPException(
            401,
            detail={"code": "webhook_unauthorized", "message": "Assinatura de webhook inválida."},
        )
    signed = timestamp_header.encode("ascii") + b"." + raw_body
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    supplied = signature_header[3:].lower()
    if not hmac.compare_digest(expected, supplied):
        raise HTTPException(
            401,
            detail={"code": "webhook_unauthorized", "message": "Assinatura de webhook inválida."},
        )
    try:
        event = PacksenviosWebhookEvent.model_validate_json(raw_body)
    except (ValidationError, ValueError):
        raise HTTPException(
            422,
            detail={"code": "webhook_payload_invalid", "message": "Payload de webhook inválido."},
        ) from None
    if delivery_header is not None and delivery_header != event.id:
        raise HTTPException(
            400,
            detail={
                "code": "webhook_delivery_id_mismatch",
                "message": "Delivery ID diverge do evento assinado.",
            },
        )
    if event.company_id != settings.webhook_company_id:
        raise HTTPException(
            403,
            detail={
                "code": "webhook_context_forbidden",
                "message": "Evento fora do contexto autorizado.",
            },
        )
    if (
        settings.webhook_location_id is not None
        and event.location_id != settings.webhook_location_id
    ):
        raise HTTPException(
            403,
            detail={
                "code": "webhook_context_forbidden",
                "message": "Evento fora do contexto autorizado.",
            },
        )
    return event


def persist_receipt(
    session: Session,
    event: PacksenviosWebhookEvent,
    raw_body: bytes,
    delivery_id: str | None,
) -> tuple[WebhookReceipt, bool]:
    body_digest = hashlib.sha256(raw_body).hexdigest()
    existing = session.scalar(select(WebhookReceipt).where(WebhookReceipt.event_id == event.id))
    if existing is not None:
        if existing.body_sha256 != body_digest:
            raise HTTPException(
                409,
                detail={
                    "code": "webhook_event_id_conflict",
                    "message": "ID de evento já recebido com outro corpo assinado.",
                },
            )
        return existing, True
    previous = None
    if event.data.shipment_id is not None:
        previous = session.scalar(
            select(func.max(WebhookReceipt.occurred_at)).where(
                WebhookReceipt.company_id == event.company_id,
                WebhookReceipt.location_id == event.location_id,
                WebhookReceipt.shipment_id == event.data.shipment_id,
            )
        )
    receipt = WebhookReceipt(
        event_id=event.id,
        delivery_id=delivery_id,
        event_type=event.type,
        occurred_at=event.occurred_at,
        company_id=event.company_id,
        location_id=event.location_id,
        shipment_id=event.data.shipment_id,
        public_code=event.data.public_code,
        dispatch_status=event.data.dispatch_status,
        body_sha256=body_digest,
        out_of_order=previous is not None and event.occurred_at < previous,
        reconciliation_status="reconciliation_pending",
        worker_status="not_configured",
        payload=event.model_dump(mode="json", by_alias=True),
    )
    session.add(receipt)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(WebhookReceipt).where(WebhookReceipt.event_id == event.id))
        if existing is None:
            raise
        if existing.body_sha256 != body_digest:
            raise HTTPException(
                409,
                detail={
                    "code": "webhook_event_id_conflict",
                    "message": "ID de evento já recebido com outro corpo assinado.",
                },
            ) from None
        return existing, True
    return receipt, False


def receipt_ack(receipt: WebhookReceipt, *, duplicate: bool) -> WebhookReceiptAck:
    return WebhookReceiptAck(
        status="duplicate" if duplicate else "accepted",
        event_id=receipt.event_id,
        reconciliation_status="reconciliation_pending",
        worker_status=receipt.worker_status,
        out_of_order=receipt.out_of_order,
    )


async def notify_reconciliation(app, session: Session, receipt: WebhookReceipt) -> None:
    notifier = getattr(app.state, "webhook_reconciliation_notifier", None)
    if notifier is None:
        return
    worker_status = "notified"
    try:
        result = notifier(receipt.id)
        if inspect.isawaitable(result):
            await result
    except Exception:
        worker_status = "unavailable"
        logger.warning("webhook reconciliation worker unavailable; receipt remains pending")
    receipt.worker_status = worker_status
    session.commit()


def list_pending_receipts(session: Session, page: int, page_size: int) -> WebhookReceiptPage:
    statement = select(WebhookReceipt).where(
        WebhookReceipt.reconciliation_status == "reconciliation_pending"
    )
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = session.scalars(
        statement.order_by(WebhookReceipt.created_at, WebhookReceipt.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return WebhookReceiptPage(
        items=[
            WebhookReceiptView(
                id=row.id,
                event_id=row.event_id,
                event_type=row.event_type,
                occurred_at=row.occurred_at,
                received_at=row.created_at,
                company_id=row.company_id,
                location_id=row.location_id,
                shipment_id=row.shipment_id,
                public_code=row.public_code,
                dispatch_status=row.dispatch_status,
                out_of_order=row.out_of_order,
                reconciliation_status=row.reconciliation_status,
                worker_status=row.worker_status,
                body_sha256=row.body_sha256,
                payload=row.payload,
            )
            for row in rows
        ],
        total=total,
    )
