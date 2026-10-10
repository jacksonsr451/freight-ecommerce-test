import re
from dataclasses import dataclass
from datetime import timedelta
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from freight_ecommerce.cart import service as carts
from freight_ecommerce.catalog.service import fail
from freight_ecommerce.domain.base import utcnow
from freight_ecommerce.domain.models import (
    Cart,
    FreightOptionSnapshot,
    FreightQuote,
    IntegrationAudit,
)
from freight_ecommerce.domain.states import CartStatus, QuoteStatus
from freight_ecommerce.freight.client import PacksenviosClient
from freight_ecommerce.freight.errors import FreightError
from freight_ecommerce.freight.logging import bind_correlation_id
from freight_ecommerce.freight.schemas import PreparedQuote, QuoteEnvelope, QuoteRequest
from freight_ecommerce.quoting.packing import derive_request
from freight_ecommerce.quoting.schemas import PublicOption, QuoteCommand, QuoteView, SelectOption


@dataclass(frozen=True)
class Dispatch:
    quote_id: UUID
    cart_id: UUID
    token: UUID
    prepared: PreparedQuote


def public_name(value: str | None, client: PacksenviosClient) -> str | None:
    secret = client.settings.api_key.get_secret_value()
    if value is not None and (
        (secret and secret in value) or re.search(r"Bearer\s+\S+", value, re.I)
    ):
        return None  # Never turn a secret echo into a browser-visible carrier name.
    return value


def project(
    session: Session, quote: FreightQuote, cart: Cart, client: PacksenviosClient
) -> QuoteView:
    status = "pending" if quote.status == QuoteStatus.REQUESTED else quote.status.value
    if quote.status == QuoteStatus.RECEIVED:
        status = quote.external_status
    options = []
    if status == "quoted":
        for option in session.scalars(
            select(FreightOptionSnapshot)
            .where(
                FreightOptionSnapshot.quote_id == quote.id,
            )
            .order_by(FreightOptionSnapshot.option_index)
        ):
            options.append(
                PublicOption(
                    reference=option.id,
                    carrier_name=public_name(option.carrier_name, client),
                    price_cents=option.price_cents,
                    deadline_days=option.deadline_days,
                    manual_only=option.manual_only,
                    demonstration_only=option.demonstration_only,
                    weight_only=option.weight_only,
                    manual_review_required=option.manual_only is not False
                    or option.demonstration_only is not False,
                )
            )
    return QuoteView(
        quote_reference=quote.id,
        cart_revision=cart.revision,
        status=status,
        mode=quote.mode,
        weight_only="length_cm" not in quote.criteria,
        options=options,
        selected_option_reference=quote.selected_option_snapshot_id if status == "quoted" else None,
    )


def load_quote(session: Session, cart: Cart, quote_id: UUID) -> FreightQuote:
    quote = session.scalar(
        select(FreightQuote)
        .where(FreightQuote.id == quote_id, FreightQuote.cart_id == cart.id)
        .with_for_update()
    )
    if quote is None:
        fail(404, "quote_not_found", "Cotação não encontrada neste carrinho.")
    return quote


def validate_cart(session: Session, cart: Cart, expected_revision: int):
    if not carts.is_editable(session, cart):
        fail(409, "cart_locked", "Carrinho encerrado; cotação bloqueada.")
    if cart.revision != expected_revision:
        fail(409, "cart_revision_conflict", "Carrinho mudou. Recarregue antes de cotar.")
    items = carts.current_items(session, cart)
    if carts.synchronize(session, cart, items):
        session.commit()
        fail(409, "cart_commercial_changed", "Catálogo mudou. Recarregue antes de cotar.")
    return items


def begin(
    engine: Engine, client: PacksenviosClient, cart_id: UUID, command: QuoteCommand
) -> Dispatch | QuoteView:
    with Session(engine, expire_on_commit=False) as session:
        cart = carts.lock_cart(session, cart_id)
        items = validate_cart(session, cart, command.expected_revision)
        try:
            draft = client.prepare_quote(
                derive_request(items, cart.delivery_address, command.packing_mode, uuid4())
            )
        except ValueError:
            fail(
                503,
                "freight_configuration_error",
                "Origem ou contexto de frete não configurados corretamente.",
            )
        quote = session.scalar(
            select(FreightQuote)
            .where(
                FreightQuote.cart_id == cart.id,
                FreightQuote.integration_scope == client.integration_scope,
                FreightQuote.cart_fingerprint == cart.commercial_fingerprint,
                FreightQuote.criteria_fingerprint == draft.criteria_fingerprint,
                FreightQuote.status != QuoteStatus.INVALIDATED,
            )
            .order_by(FreightQuote.created_at.desc(), FreightQuote.id)
            .limit(1)
            .with_for_update()
        )
        if quote is not None and not command.refresh:
            if quote.status == QuoteStatus.RECEIVED:
                result = project(session, quote, cart, client)
                session.commit()
                return result
        # Provider quota/maintenance is not bypassed by changing criteria or generating a new key.
        retry_at = session.scalar(
            select(func.max(FreightQuote.retry_not_before)).where(
                FreightQuote.integration_scope == client.integration_scope,
                FreightQuote.retry_not_before > utcnow(),
            )
        )
        if retry_at is not None:
            seconds = max(1, int((retry_at - utcnow()).total_seconds()) + 1)
            raise HTTPException(
                429,
                detail={
                    "code": "freight_retry_wait",
                    "message": "Aguarde antes de repetir a chamada de frete.",
                },
                headers={"Retry-After": str(seconds)},
            )
        if quote is not None and not command.refresh:
            if quote.status == QuoteStatus.FAILED:
                fail(
                    409,
                    "quote_failed",
                    "Tentativa falhou. Corrija a condição e solicite refresh explícito.",
                )
            if quote.inflight_token is not None and quote.inflight_until > utcnow():
                result = project(session, quote, cart, client)
                session.commit()
                return result
            prepared = client.prepare_quote(
                QuoteRequest.model_validate_json(quote.prepared_payload)
            )
            if (
                prepared.payload != quote.prepared_payload
                or prepared.criteria_fingerprint != draft.criteria_fingerprint
            ):
                fail(
                    409,
                    "quote_context_changed",
                    "Payload salvo não corresponde aos critérios atuais.",
                )
        else:
            carts.invalidate_open_quotes(session, cart)
            prepared = draft
            criteria = QuoteRequest.model_validate_json(prepared.payload).model_dump(
                mode="json",
                exclude={"request_key"},
                exclude_none=True,
            )
            quote = FreightQuote(
                cart_id=cart.id,
                integration_scope=client.integration_scope,
                request_key=prepared.request_key,
                criteria=criteria,
                prepared_payload=prepared.payload,
                criteria_fingerprint=prepared.criteria_fingerprint,
                cart_fingerprint=cart.commercial_fingerprint,
                mode=client.settings.mode,
            )
            session.add(quote)
            session.flush()
        token = uuid4()
        quote.inflight_token = token
        seconds = (
            client.settings.max_attempts
            * (3 * client.settings.timeout_seconds + client.settings.connect_timeout_seconds)
            + client.settings.max_retry_wait_seconds
            + 5
        )
        quote.inflight_until = utcnow() + timedelta(seconds=seconds)
        quote.last_error_code = None
        quote.retry_not_before = None
        if cart.status == CartStatus.ACTIVE:
            cart.transition(CartStatus.CHECKOUT_PENDING)
        session.add(
            IntegrationAudit(
                correlation_id=token,
                quote_id=quote.id,
                mode=quote.mode,
                operation="quote",
                outcome="started",
                request_key=quote.request_key,
                details={"packing_mode": command.packing_mode},
            )
        )
        session.commit()  # Durable key + exact bytes BEFORE any outbound HTTP, release cart lock.
        return Dispatch(quote.id, cart.id, token, prepared)


def is_current(
    session: Session, cart: Cart, quote: FreightQuote, client: PacksenviosClient
) -> bool:
    if not carts.is_editable(session, cart):
        return False
    items = carts.current_items(session, cart)
    carts.synchronize(session, cart, items)
    if quote.status == QuoteStatus.INVALIDATED:
        return False
    packing = "equal_volumes" if "length_cm" in quote.criteria else "weight_only"
    try:
        request = derive_request(items, cart.delivery_address, packing, quote.request_key)
        prepared = client.prepare_quote(request)
    except (HTTPException, ValueError):
        quote.transition(QuoteStatus.INVALIDATED)
        return False
    if (
        quote.cart_fingerprint != cart.commercial_fingerprint
        or quote.integration_scope != client.integration_scope
        or quote.criteria_fingerprint != prepared.criteria_fingerprint
    ):
        quote.transition(QuoteStatus.INVALIDATED)
        return False
    return True


def complete(
    engine: Engine,
    client: PacksenviosClient,
    dispatch: Dispatch,
    response: QuoteEnvelope | None,
    error: FreightError | None,
    elapsed_ms: int,
) -> QuoteView:
    with Session(engine, expire_on_commit=False) as session:
        cart = carts.lock_cart(session, dispatch.cart_id)
        quote = load_quote(session, cart, dispatch.quote_id)
        if quote.inflight_token != dispatch.token:
            result = project(session, quote, cart, client)
            session.commit()
            return result  # Superseded worker cannot overwrite a newer claim/receipt.
        current = is_current(session, cart, quote, client)
        quote.inflight_token = None
        quote.inflight_until = None
        if error is not None:
            quote.last_error_code = error.code
            transient = error.code in {
                "timeout",
                "transport_error",
                "invalid_response",
            } or error.http_status in {429, 503}
            if error.http_status in {429, 503} and error.retry_after_seconds is not None:
                try:
                    quote.retry_not_before = utcnow() + timedelta(seconds=error.retry_after_seconds)
                except OverflowError:
                    transient = False
            if current and not transient:
                quote.transition(QuoteStatus.FAILED)
            outcome = "uncertain" if transient else "failed"
        else:
            quote.external_quote_request_id = response.data.id
            quote.external_status = response.data.status
            quote.response = response.model_dump(mode="json", exclude_unset=True)
            weight_only = "length_cm" not in quote.criteria
            for index, option in enumerate(response.data.options):
                session.add(
                    FreightOptionSnapshot(
                        quote_id=quote.id,
                        option_index=index,
                        price_cents=option.price_cents,
                        deadline_days=option.deadline_days,
                        carrier_name=option.carrier_name,
                        manual_only=option.manual_only,
                        demonstration_only=option.demonstration_only,
                        weight_only=weight_only,
                        payload=option.model_dump(mode="json", exclude_unset=True),
                    )
                )
            if current:
                quote.transition(QuoteStatus.RECEIVED)
            outcome = "succeeded" if current else "uncertain"
        session.add(
            IntegrationAudit(
                correlation_id=dispatch.token,
                quote_id=quote.id,
                mode=quote.mode,
                operation="quote",
                outcome=outcome,
                request_key=quote.request_key,
                http_status=error.http_status if error else 200,
                latency_ms=elapsed_ms,
                details={
                    "code": error.code if error else "received",
                    "current": current,
                    "retry_after_seconds": error.retry_after_seconds if error else None,
                },
            )
        )
        session.flush()
        result = project(session, quote, cart, client)
        session.commit()
        if not current:
            fail(
                409,
                "quote_criteria_changed",
                "Resposta pertence a critérios antigos; recote o carrinho.",
            )
        return result


async def quote_cart(
    engine: Engine, client: PacksenviosClient, cart_id: UUID, command: QuoteCommand
) -> QuoteView:
    dispatch = begin(engine, client, cart_id, command)
    if isinstance(dispatch, QuoteView):
        return dispatch
    response = None
    error = None
    started = perf_counter()
    try:
        with bind_correlation_id(str(dispatch.token)):
            response = await client.create_quote(dispatch.prepared)
        if response.data.status not in {"quoted", "unavailable", "fiscal_review"}:
            error = FreightError(
                "unexpected_quote_state",
                "Estado de criação de cotação não suportado.",
                http_status=200,
            )
            response = None
        elif any(
            option.price_cents > 2**63 - 1
            or (option.deadline_days is not None and option.deadline_days > 2**31 - 1)
            for option in response.data.options
        ):
            error = FreightError(
                "invalid_response",
                "Valores de cotação excedem a capacidade de armazenamento.",
                http_status=200,
            )
            response = None
    except FreightError as caught:
        error = caught
    result = complete(
        engine, client, dispatch, response, error, int((perf_counter() - started) * 1000)
    )
    if error is not None:
        status = (
            error.http_status
            if error.http_status in {401, 403, 409, 422, 429, 503}
            else (504 if error.code == "timeout" else 502)
        )
        headers = {}
        if error.retry_after_seconds is not None and error.retry_after_seconds < 2**31:
            headers["Retry-After"] = str(
                int(error.retry_after_seconds) + (error.retry_after_seconds % 1 > 0)
            )
        raise HTTPException(
            status, detail={"code": f"freight_{error.code}", "message": str(error)}, headers=headers
        )
    return result


def get_quote(
    engine: Engine, client: PacksenviosClient, cart_id: UUID, quote_id: UUID
) -> QuoteView:
    with Session(engine, expire_on_commit=False) as session:
        cart = carts.lock_cart(session, cart_id)
        quote = load_quote(session, cart, quote_id)
        if quote.status != QuoteStatus.INVALIDATED:
            is_current(session, cart, quote, client)
        result = project(session, quote, cart, client)
        session.commit()
        return result


def select_option(
    engine: Engine, client: PacksenviosClient, cart_id: UUID, quote_id: UUID, command: SelectOption
) -> QuoteView:
    with Session(engine, expire_on_commit=False) as session:
        cart = carts.lock_cart(session, cart_id)
        validate_cart(session, cart, command.expected_revision)
        quote = load_quote(session, cart, quote_id)
        if not is_current(session, cart, quote, client):
            session.commit()
            fail(409, "quote_criteria_changed", "Cotação não corresponde ao carrinho atual.")
        if quote.status != QuoteStatus.RECEIVED or quote.external_status != "quoted":
            fail(409, "quote_not_selectable", "Cotação ainda não possui ofertas utilizáveis.")
        option = session.scalar(
            select(FreightOptionSnapshot).where(
                FreightOptionSnapshot.id == command.option_reference,
                FreightOptionSnapshot.quote_id == quote.id,
            )
        )
        if option is None:
            fail(404, "option_not_found", "Referência não pertence à cotação deste carrinho.")
        if option.weight_only:
            fail(409, "estimate_not_selectable", "Estimativa weight_only não pode fechar pedido.")
        quote.selected_option_snapshot_id = (
            option.id
        )  # Local reference only, not Packsenvios selection.
        result = project(session, quote, cart, client)
        session.commit()
        return result
