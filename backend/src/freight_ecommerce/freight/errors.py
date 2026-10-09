from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

CONFLICT_MESSAGE = "Esta chave já foi usada com outra cotação."
MESSAGES = {
    401: ("unauthorized", "Credencial de frete inválida."),
    403: ("forbidden", "Acesso de frete recusado."),
    404: ("not_found", "Cotação não encontrada no contexto autorizado."),
    409: ("conflict", "Estado de frete incompatível."),
    422: ("validation_error", "Critérios de frete recusados."),
    429: ("rate_limited", "Limite de chamadas de frete atingido."),
    503: ("unavailable", "Serviço de frete temporariamente indisponível."),
}


class FreightError(Exception):
    """Local normalized error; never retain HTTP request, response or raw exception/body."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int | None = None,
        retry_after_seconds: float | None = None,
        fields: tuple[str, ...] = (),
    ):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.retry_after_seconds = retry_after_seconds
        self.fields = fields


def parse_retry_after(value: str | None, now: datetime) -> float | None:
    if not value:
        return None
    if value.isascii() and value.isdigit():
        try:
            return int(value)
        except (ValueError, OverflowError):
            return None
    try:
        target = parsedate_to_datetime(value)
        if target.tzinfo is None:
            return None
        return max(0.0, (target.astimezone(UTC) - now.astimezone(UTC)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None
