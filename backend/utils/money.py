"""Rounding and minor-unit conversion.

Services compute in rials as floats, round to 2 decimals the way the prototype did,
and the database stores integer minor units.
"""

import math


def r2(x: float) -> float:
    """Round half away from zero to 2 decimals (matches the prototype's Math.round)."""
    v = float(x or 0)
    return math.floor(v * 100 + 0.5 + 1e-9) / 100 if v >= 0 else -math.floor(-v * 100 + 0.5 + 1e-9) / 100


def to_minor(x: float | None) -> int:
    return int(round(r2(x or 0) * 100))


def from_minor(x: int | None) -> float:
    return (x or 0) / 100


def is_num(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
