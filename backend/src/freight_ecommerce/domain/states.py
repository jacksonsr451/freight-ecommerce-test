from enum import StrEnum
from typing import ClassVar

from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, validates


class TransitionError(ValueError):
    pass


class CartStatus(StrEnum):
    ACTIVE = "active"
    CHECKOUT_PENDING = "checkout_pending"
    CHECKED_OUT = "checked_out"
    ABANDONED = "abandoned"


class CheckoutStatus(StrEnum):
    CREATED = "created"
    QUOTING = "quoting"
    QUOTED = "quoted"
    UNAVAILABLE = "quote_unavailable"
    FISCAL_REVIEW = "quote_fiscal_review"
    CONFIRMED = "confirmed"
    INVALIDATED = "invalidated"
    FAILED = "failed"


class QuoteStatus(StrEnum):
    REQUESTED = "requested"
    RECEIVED = "received"
    FAILED = "failed"
    INVALIDATED = "invalidated"


class OrderStatus(StrEnum):
    PAYMENT_PENDING = "payment_pending"
    PAID_SIMULATED = "paid_simulated"
    PAYMENT_DECLINED = "payment_declined"
    CANCELLED = "cancelled"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"


class FulfillmentStatus(StrEnum):
    PAID_SIMULATED = "pago_simulado"
    PICKING = "separando"
    PACKED = "embalado"
    READY_FOR_IMPORT = "pronto_para_importacao"
    IMPORT_PENDING = "importacao_pendente"
    SHIPPED_SIMULATED = "expedido_simulado"
    DELIVERED_SIMULATED = "entregue_simulado"
    CANCELLED = "cancelado"


class ImportStatus(StrEnum):
    PREPARED = "prepared"
    UPLOAD_PENDING = "upload_pending"
    VALIDATING = "validating"
    READY_FOR_CONFIRMATION = "ready_for_confirmation"
    CONFIRMATION_PENDING = "confirmation_pending"
    IMPORTED = "imported"
    DISPATCH_PENDING = "dispatch_pending"
    COMPLETED = "completed"
    FAILED = "failed"


TRANSITIONS = {
    CartStatus: {
        CartStatus.ACTIVE: {CartStatus.CHECKOUT_PENDING, CartStatus.ABANDONED},
        CartStatus.CHECKOUT_PENDING: {
            CartStatus.ACTIVE,
            CartStatus.CHECKED_OUT,
            CartStatus.ABANDONED,
        },
    },
    CheckoutStatus: {
        CheckoutStatus.CREATED: {CheckoutStatus.QUOTING, CheckoutStatus.INVALIDATED},
        CheckoutStatus.QUOTING: {
            CheckoutStatus.QUOTED,
            CheckoutStatus.UNAVAILABLE,
            CheckoutStatus.FISCAL_REVIEW,
            CheckoutStatus.FAILED,
            CheckoutStatus.INVALIDATED,
        },
        CheckoutStatus.QUOTED: {CheckoutStatus.CONFIRMED, CheckoutStatus.INVALIDATED},
        CheckoutStatus.UNAVAILABLE: {CheckoutStatus.INVALIDATED},
        CheckoutStatus.FISCAL_REVIEW: {CheckoutStatus.INVALIDATED},
        CheckoutStatus.FAILED: {CheckoutStatus.INVALIDATED},
    },
    QuoteStatus: {
        QuoteStatus.REQUESTED: {QuoteStatus.RECEIVED, QuoteStatus.FAILED, QuoteStatus.INVALIDATED},
        QuoteStatus.RECEIVED: {QuoteStatus.INVALIDATED},
        QuoteStatus.FAILED: {QuoteStatus.INVALIDATED},
    },
    OrderStatus: {
        OrderStatus.PAYMENT_PENDING: {
            OrderStatus.PAID_SIMULATED,
            OrderStatus.PAYMENT_DECLINED,
            OrderStatus.CANCELLED,
        },
        OrderStatus.PAID_SIMULATED: {OrderStatus.CANCELLED},
        OrderStatus.PAYMENT_DECLINED: {OrderStatus.CANCELLED},
    },
    PaymentStatus: {PaymentStatus.PENDING: {PaymentStatus.APPROVED, PaymentStatus.DECLINED}},
    FulfillmentStatus: {
        FulfillmentStatus.PAID_SIMULATED: {FulfillmentStatus.PICKING, FulfillmentStatus.CANCELLED},
        FulfillmentStatus.PICKING: {FulfillmentStatus.PACKED, FulfillmentStatus.CANCELLED},
        FulfillmentStatus.PACKED: {
            FulfillmentStatus.READY_FOR_IMPORT,
            FulfillmentStatus.SHIPPED_SIMULATED,
            FulfillmentStatus.CANCELLED,
        },
        FulfillmentStatus.READY_FOR_IMPORT: {FulfillmentStatus.IMPORT_PENDING},
        FulfillmentStatus.IMPORT_PENDING: {
            FulfillmentStatus.READY_FOR_IMPORT,
            FulfillmentStatus.SHIPPED_SIMULATED,
        },
        FulfillmentStatus.SHIPPED_SIMULATED: {FulfillmentStatus.DELIVERED_SIMULATED},
    },
    ImportStatus: {
        ImportStatus.PREPARED: {ImportStatus.UPLOAD_PENDING},
        ImportStatus.UPLOAD_PENDING: {ImportStatus.VALIDATING, ImportStatus.FAILED},
        ImportStatus.VALIDATING: {ImportStatus.READY_FOR_CONFIRMATION, ImportStatus.FAILED},
        ImportStatus.READY_FOR_CONFIRMATION: {ImportStatus.CONFIRMATION_PENDING},
        ImportStatus.CONFIRMATION_PENDING: {ImportStatus.IMPORTED, ImportStatus.FAILED},
        ImportStatus.IMPORTED: {ImportStatus.DISPATCH_PENDING},
        ImportStatus.DISPATCH_PENDING: {ImportStatus.COMPLETED, ImportStatus.FAILED},
    },
}


def state_column(enum_type: type[StrEnum], initial: StrEnum):
    return mapped_column(
        SQLAlchemyEnum(
            enum_type,
            values_callable=lambda members: [member.value for member in members],
            native_enum=False,
            create_constraint=True,
            name=enum_type.__name__.lower(),
        ),
        default=initial,
        server_default=initial.value,
        nullable=False,
    )


class Stateful:
    initial_status: ClassVar[StrEnum]
    version: Mapped[int] = mapped_column(default=1, nullable=False)

    @declared_attr.directive
    def __mapper_args__(cls):
        return {"version_id_col": cls.version}

    @validates("status")
    def validate_status(self, key, value):
        enum_type = type(self.initial_status)
        if isinstance(value, StrEnum) and not isinstance(value, enum_type):
            raise TransitionError("State belongs to another lifecycle")
        try:
            target = enum_type(value)
        except (ValueError, TypeError) as error:
            raise TransitionError("Unknown local state") from error
        current = getattr(self, "status", None) or self.initial_status
        if target != current and target not in TRANSITIONS[enum_type].get(current, set()):
            raise TransitionError(f"Invalid local transition: {current} -> {target}")
        return target

    def transition(self, target: StrEnum) -> None:
        self.status = target
