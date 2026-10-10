from uuid import uuid4

import testrunner
from fastapi import HTTPException

from freight_ecommerce.cart.schemas import CartItemView
from freight_ecommerce.quoting.packing import derive_request

ADDRESS = {
    "postal_code": "01001000",
    "street": "Rua sintética",
    "number": "1",
    "district": "Centro",
    "city": "São Paulo",
    "state": "SP",
}


def item(**overrides):
    return CartItemView(
        **{
            "id": uuid4(),
            "product_id": uuid4(),
            "sku": "SYNTHETIC",
            "name": "Synthetic",
            "quantity": 2,
            "unit_price_cents": 4590,
            "line_total_cents": 9180,
            "weight_grams": 450,
            "line_weight_grams": 900,
            "length_cm": 23,
            "width_cm": 16,
            "height_cm": 3,
            "available_quantity": 12,
            "problem": None,
            **overrides,
        }
    )


def test_equal_geometry_different_individual_weights_are_not_rounded_or_guessed():
    second = item(
        quantity=1,
        unit_price_cents=1000,
        line_total_cents=1000,
        weight_grams=220,
        line_weight_grams=220,
    )
    request = derive_request([item(), second], ADDRESS, "equal_volumes", uuid4())
    assert request.weight_kg == "1.120" and request.declared_value_cents == 10180
    assert request.volume_count == 3
    assert [volume.weight_grams for volume in request.volumes] == [450, 450, 220]
    assert all(volume.length_cm == 23 for volume in request.volumes)


@testrunner.mark.parametrize("postal", ["01001-000", "1001000", 1001000, "invalid"])
def test_engine_requires_canonical_destination_and_preserves_leading_zero(postal):
    with testrunner.raises(HTTPException) as error:
        derive_request([item()], {**ADDRESS, "postal_code": postal}, "equal_volumes", uuid4())
    assert error.value.status_code == 422 and error.value.detail["code"] == "invalid_cart_address"


@testrunner.mark.parametrize(
    "items,mode,code",
    [
        ([item(), item(length_cm=16, width_cm=23)], "equal_volumes", "unequal_volumes"),
        ([item(quantity=1001)], "equal_volumes", "volume_limit"),
        ([item(line_total_cents=100_000_001)], "equal_volumes", "quote_limits"),
        ([item(line_weight_grams=50_000_001)], "weight_only", "quote_limits"),
    ],
)
def test_unrepresentable_volumes_and_quote_limits_do_not_invent_geometry(items, mode, code):
    with testrunner.raises(HTTPException) as error:
        derive_request(items, ADDRESS, mode, uuid4())
    assert error.value.status_code == 422 and error.value.detail["code"] == code
