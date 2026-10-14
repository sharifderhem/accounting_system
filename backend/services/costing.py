"""Pure factory formulas (spec §2, §7.2, §8). No database access here."""

from typing import Any

from utils.dates import add_years
from utils.money import r2

S = dict[str, Any]


def rm_kg_cost(s: S) -> float:
    """Standard HDPE cost per kg in YER."""
    return s["rmPriceSarTon"] / 1000 * s["fx"]


def pig_bag_kg(s: S) -> float:
    """kg in one pigment bag (e.g. 1500/25 × 30 g = 1.8 kg)."""
    return s["pigmentCoverKg"] / s["bagKg"] * s["pigmentGPerBag"] / 1000


def pig_kg_cost(s: S) -> float:
    """Standard pigment cost per kg in YER."""
    return s["pigmentPriceSar"] * s["fx"] / pig_bag_kg(s)


def cartons_per_minute(s: S) -> float:
    return 60 / s["cycleSec"] * s["cavities"] / s["capsPerCarton"]


def capacity_day(s: S) -> float:
    return 86400 / s["cycleSec"] * s["cavities"] / s["capsPerCarton"]


def max_cartons_shift(s: S) -> float:
    return s["shiftHours"] * 3600 / s["cycleSec"] * s["cavities"] / s["capsPerCarton"]


def chiller_kwh(s: S, hours: float) -> float:
    return s["chillerKw"] * s["chillerLoad"] * hours


def pigment_kg_for(s: S, rm_kg: float) -> float:
    return rm_kg / s["bagKg"] * s["pigmentGPerBag"] / 1000


# ---- depreciation (§8) ----

def asset_end(a: dict[str, Any]) -> str:
    return add_years(a["date"], a.get("life") or 5)


def asset_active(a: dict[str, Any], date: str) -> bool:
    return (a.get("cost") or 0) > 0 and a["date"] <= date <= asset_end(a)


def asset_daily(a: dict[str, Any]) -> float:
    return ((a.get("cost") or 0) - (a.get("salvage") or 0)) / ((a.get("life") or 5) * 365)


def dep_daily(assets: list[dict[str, Any]], date: str) -> float:
    return sum(asset_daily(a) for a in assets if asset_active(a, date))


def with_labor_delta(cost: dict[str, Any], cartons: float, delta: float, s: S) -> dict[str, Any]:
    """A shift's stored cost after wages are added to (or removed from) it later."""
    out = dict(cost or {})
    out["labor"] = r2((out.get("labor") or 0) + delta)
    out["total"] = r2((out.get("total") or 0) + delta)
    if cartons:
        out["per"] = r2(out["total"] / cartons)
        out["perSar"] = r2(out["per"] / s["fx"])
        out["marginSar"] = r2(s["priceSar"] - out["per"] / s["fx"])
    return out
