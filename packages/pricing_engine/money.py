"""Money primitives. All money is Decimal; binary floats are rejected outright."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer

RIAL_PER_TOMAN = Decimal(10)
ZERO = Decimal(0)


class FloatMoneyError(TypeError):
    """Raised when a binary float reaches a money/quantity field."""


def to_decimal(value: Any) -> Decimal:
    """Convert int/str/Decimal to Decimal. Floats are refused: they cannot represent prices exactly."""
    if isinstance(value, bool):
        raise TypeError("bool is not a number")
    if isinstance(value, float):
        raise FloatMoneyError(f"binary float {value!r} is not allowed for money; pass a str or Decimal")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation as exc:
            raise ValueError(f"not a decimal number: {value!r}") from exc
    raise TypeError(f"cannot convert {type(value).__name__} to Decimal")


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return to_decimal(value)


def _serialize(value: Decimal | None) -> str | None:
    return None if value is None else format(value.normalize(), "f")


# Pydantic field type: exact Decimal in, exact string out (JSON never carries a float).
Dec = Annotated[Decimal, BeforeValidator(to_decimal), PlainSerializer(_serialize, return_type=str | None)]
OptDec = Annotated[
    Decimal | None, BeforeValidator(_optional_decimal), PlainSerializer(_serialize, return_type=str | None)
]


def toman_to_rial(toman: Decimal) -> Decimal:
    return to_decimal(toman) * RIAL_PER_TOMAN


def rial_to_toman(rial: Decimal) -> Decimal:
    return to_decimal(rial) / RIAL_PER_TOMAN


def dsum(values) -> Decimal:
    total = ZERO
    for v in values:
        total += v
    return total
