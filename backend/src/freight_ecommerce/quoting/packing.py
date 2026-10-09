from uuid import UUID

from pydantic import ValidationError

from freight_ecommerce.cart.schemas import CartItemView, DeliveryAddress
from freight_ecommerce.catalog.service import fail
from freight_ecommerce.freight.schemas import QuoteRequest, Volume


def derive_request(
    items: list[CartItemView], address: dict | None, packing_mode: str, request_key: UUID
) -> QuoteRequest:
    if not items or any(item.problem is not None for item in items):
        fail(409, "cart_not_quotable", "Carrinho vazio ou com produtos indisponíveis.")
    try:
        destination = DeliveryAddress.model_validate(address)
    except ValidationError:
        fail(422, "invalid_cart_address", "Destino deve ter endereço válido e CEP de 8 dígitos.")
    grams = sum(item.line_weight_grams for item in items)
    value = sum(item.line_total_cents for item in items)
    fields = {}
    if packing_mode == "equal_volumes":
        shapes = {(item.length_cm, item.width_cm, item.height_cm) for item in items}
        if len(shapes) != 1:
            fail(
                422,
                "unequal_volumes",
                "Volumes divergentes não possuem dimensões agregadas fiéis. "
                "Use estimativa weight_only explicitamente.",
            )
        count = sum(item.quantity for item in items)
        if count > 1000:
            fail(422, "volume_limit", "Cotação aceita no máximo 1000 volumes.")
        length, width, height = next(iter(shapes))
        fields = {
            "length_cm": length,
            "width_cm": width,
            "height_cm": height,
            "volume_count": count,
            "volumes": tuple(
                Volume(
                    weight_grams=item.weight_grams,
                    length_cm=item.length_cm,
                    width_cm=item.width_cm,
                    height_cm=item.height_cm,
                )
                for item in items
                for _ in range(item.quantity)
            ),
        }
    elif packing_mode != "weight_only":
        fail(422, "invalid_packing_mode", "Política de volumes local desconhecida.")
    try:
        return QuoteRequest(
            request_key=request_key,
            destination_postal_code=destination.postal_code,
            weight_kg=f"{grams // 1000}.{grams % 1000:03d}",
            declared_value_cents=value,
            **fields,
        )
    except ValidationError:
        fail(422, "quote_limits", "Peso, valor ou dimensões ultrapassam os limites da cotação.")
