import logging
from contextlib import contextmanager
from contextvars import ContextVar

transport_logging_scope: ContextVar[bool] = ContextVar(
    "freight_transport_logging_scope", default=False
)
correlation_id_scope: ContextVar[str | None] = ContextVar("freight_correlation_id", default=None)


@contextmanager
def bind_correlation_id(value: str):
    token = correlation_id_scope.set(value)
    try:
        yield
    finally:
        correlation_id_scope.reset(token)


class ScopedTransportFilter(logging.Filter):
    """Suppress arbitrary transport diagnostics only during this adapter's requests."""

    def filter(self, record):
        if transport_logging_scope.get():
            record.msg = "freight_http_transport_event"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return True


def protect_transport_logs() -> None:
    # No level/handler changes and no secret stored globally; unrelated requests stay unchanged.
    for name in (
        "httpx",
        "httpcore",
        "httpcore.connection",
        "httpcore.connection_pool",
        "httpcore.http11",
        "httpcore.http2",
        "httpcore.proxy",
        "httpcore.socks",
    ):
        logger = logging.getLogger(name)
        if not any(isinstance(filter_, ScopedTransportFilter) for filter_ in logger.filters):
            logger.addFilter(ScopedTransportFilter())
