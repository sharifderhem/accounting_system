"""Current production rates, used by forecasts, stock cover and break-even.

From the last 14 approved shifts when they exist, otherwise from the plan in Settings
(as the prototype did).
"""

import sqlite3
from typing import Any

from repositories import shifts_repo
from services import ledger_service
from services.costing import chiller_kwh, pigment_kg_for

# Machine kWh per day assumed before any shift is approved (prototype constant).
PLANNED_MACHINE_KWH_DAY = 436


def production_rates(conn: sqlite3.Connection, s: dict[str, Any]) -> dict[str, Any]:
    recent = [x for x in shifts_repo.list_all(conn, status="approved", limit=14) if x.get("cost")]
    per_day = 24 / s["shiftHours"]
    if recent:
        n = len(recent)
        car = sum(x["cartons"] or 0 for x in recent) / n * per_day
        rm = sum(x["cost"].get("rmKg") or 0 for x in recent) / n * per_day
        kwh = sum(x["cost"].get("kwh") or 0 for x in recent) / n * per_day
        return {"src": f"آخر {n} وردية معتمدة", "car": car, "rm": rm, "pig": pigment_kg_for(s, rm), "kwh": kwh, "shifts": n}
    car = float(s.get("plannedCartonsDay") or 50)
    rm = car * s["cartonNetKg"] * 1.03
    return {"src": "الخطة في الإعدادات", "car": car, "rm": rm, "pig": pigment_kg_for(s, rm),
            "kwh": PLANNED_MACHINE_KWH_DAY + chiller_kwh(s, 24), "shifts": 0}


def stock_days(conn: sqlite3.Connection, s: dict[str, Any]) -> dict[str, float | None]:
    r = production_rates(conn, s)
    return {
        "1301": ledger_service.bal(conn, "1301")["q"] / r["rm"] if r["rm"] else None,
        "1302": ledger_service.bal(conn, "1302")["q"] / r["pig"] if r["pig"] else None,
        "1303": ledger_service.bal(conn, "1303")["q"] / r["car"] if r["car"] else None,
    }
