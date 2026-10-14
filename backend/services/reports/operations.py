"""Production and planning reports: cost, cash forecast, FX risk, break-even, budget, efficiency."""

import sqlite3
from typing import Any

from database import transaction
from repositories import assets_repo, entries_repo, settings_repo, shifts_repo
from services import ledger_service, settings_service
from services.costing import (
    capacity_day, cartons_per_minute, chiller_kwh, dep_daily, pig_bag_kg, pig_kg_cost, pigment_kg_for, rm_kg_cost,
)
from services.chart import MONEY_ACCOUNTS
from services.rates_service import production_rates
from services.reports.statements import period
from utils.dates import add_days, today
from utils.errors import need
from utils.money import is_num, r2

DEFAULT_DAILY_WAGES = 50000


def _approved(conn: sqlite3.Connection, since: str | None = None, until: str | None = None) -> list[dict[str, Any]]:
    return [x for x in shifts_repo.list_all(conn, status="approved", since=since, until=until) if x.get("cost")]


def _shift_row(x: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
    c = x["cost"]
    return {"date": x["date"], "shift": x["shift"], "cartons": x["cartons"], "rmKg": c.get("rmKg"), "kwh": c.get("kwh"),
            "total": c.get("total"), "perSar": c.get("perSar"), "marginSar": r2(s["priceSar"] - (c.get("perSar") or 0)),
            "eff": c.get("eff"), "downMin": c.get("downMin") or 0, "downReason": c.get("downReason") or "",
            "lost": r2((c.get("lostDown") or 0) + (c.get("lostOther") or 0))}


def _avg_daily_expenses(conn: sqlite3.Connection, days_back: int, accounts: tuple[str, ...]) -> float | None:
    since = add_days(today(), -days_back)
    total = entries_repo.sums(conn, accounts=accounts, src="exp", since=since)["y"]
    days = {e["date"] for e in entries_repo.entries_where(conn, ["e.src = 'exp'", "e.date >= ?"], [since])}
    return total / len(days) if days else None


# ---------------------------------------------------------------- 6. production cost

def production_cost(conn: sqlite3.Connection, **_: Any) -> dict[str, Any]:
    s = settings_service.get(conn)
    shifts = _approved(conn)
    cartons = sum(x["cartons"] or 0 for x in shifts)
    total = sum(x["cost"].get("total") or 0 for x in shifts)
    kwh = sum(x["cost"].get("kwh") or 0 for x in shifts)
    rm = sum(x["cost"].get("rmKg") or 0 for x in shifts)
    return {
        "fx": s["fx"], "cartonNetKg": s["cartonNetKg"], "capacityDay": r2(capacity_day(s)), "cavities": s["cavities"],
        "cycleSec": s["cycleSec"], "chillerKw": s["chillerKw"], "chillerLoad": s["chillerLoad"],
        "totals": {"cartons": cartons, "perYer": r2(total / cartons) if cartons else None,
                   "perSar": r2(total / cartons / s["fx"]) if cartons else None,
                   "rmPerCarton": r2(rm / cartons) if cartons else None, "kwhPerCarton": r2(kwh / cartons) if cartons else None},
        "rows": [_shift_row(x, s) for x in shifts],
    }


# ---------------------------------------------------------------- 7. cash forecast

def cash_forecast(conn: sqlite3.Connection, horizon: int | None = None, cartons: float | None = None, **_: Any) -> dict[str, Any]:
    s = settings_service.get(conn)
    r = production_rates(conn, s)
    horizon = int(horizon or 14)
    horizon = horizon if horizon in (7, 14, 30) else 14
    fx = s["fx"]
    car = float(cartons) if cartons else r["car"]
    scale = car / (r["car"] or car or 1)
    start = sum(ledger_service.bal(conn, a)["y"] for a in MONEY_ACCOUNTS)
    recv = max(0.0, ledger_service.bal(conn, "1201")["fc"]) * fx
    cd = max(1, int(s.get("collectionDays") or 7))
    rm_day = scale * r["rm"]
    pig_day = pigment_kg_for(s, rm_day)
    cover = {
        "rm": max(0.0, ledger_service.bal(conn, "1301")["q"]) / rm_day if rm_day else 0,
        "pig": max(0.0, ledger_service.bal(conn, "1302")["q"]) / pig_day if pig_day else 0,
        "ct": max(0.0, ledger_service.bal(conn, "1303")["q"]) / car if car else 0,
    }
    elec_day = r["kwh"] * s["kwhPrice"] * scale
    pre_left = max(0.0, ledger_service.bal(conn, "1401")["y"])
    wages = _avg_daily_expenses(conn, 14, ("5201", "5203", "6101")) or DEFAULT_DAILY_WAGES
    bal = start
    low, low_day = start, today()
    rows = []
    for d in range(1, horizon + 1):
        day = add_days(today(), d)
        inflow = (recv / cd if d <= cd else 0) + (car * s["priceSar"] * fx if d > cd else 0)
        materials = ((rm_day * rm_kg_cost(s) if d > cover["rm"] else 0) + (pig_day * pig_kg_cost(s) if d > cover["pig"] else 0)
                     + (car * s["cartonCost"] if d > cover["ct"] else 0))
        if pre_left >= elec_day:
            pre_left -= elec_day
            elec = 0.0
        else:
            elec, pre_left = elec_day - pre_left, 0.0
        bal += inflow - materials - elec - wages
        if bal < low:
            low, low_day = bal, day
        rows.append({"date": day, "in": r2(inflow), "materials": r2(materials), "electricity": r2(elec), "wages": r2(wages),
                     "balance": r2(bal)})
    return {"horizon": horizon, "cartons": r2(car), "source": r["src"], "start": r2(start), "lowest": r2(low),
            "lowestDate": low_day, "end": r2(bal), "fx": fx, "cover": {k: r2(v) for k, v in cover.items()},
            "dailyWages": r2(wages), "collectionDays": cd, "rows": rows}


# ---------------------------------------------------------------- 9. FX risk

def fx_risk(conn: sqlite3.Connection, **_: Any) -> dict[str, Any]:
    s = settings_service.get(conn)
    r = production_rates(conn, s)
    fx = s["fx"]
    car = r["car"] * 30
    rev_sar = car * s["priceSar"]
    rm_sar = r["rm"] * 30 * s["rmPriceSarTon"] / 1000
    pig_sar = r["pig"] * 30 * s["pigmentPriceSar"] / pig_bag_kg(s)
    yer_exp = (_avg_daily_expenses(conn, 30, ("5201", "5203", "6101")) or DEFAULT_DAILY_WAGES) * 30
    yer_elec = r["kwh"] * 30 * s["kwhPrice"]
    yer_cart = car * s["cartonCost"]
    yer_dep = dep_daily(assets_repo.list_all(conn), today()) * 30
    yer_total = yer_exp + yer_elec + yer_cart + yer_dep
    scenarios = []
    for delta in (-10, -5, 0, 5, 10):
        f = fx + delta
        profit_sar = rev_sar - rm_sar - pig_sar - yer_total / f
        scenarios.append({"fx": f, "profitSar": r2(profit_sar), "profitYer": r2(profit_sar * f), "today": delta == 0})
    base = scenarios[2]["profitSar"]
    for sc in scenarios:
        sc["diffSar"] = r2(sc["profitSar"] - base)
    return {"fx": fx, "cartonsDay": r2(r["car"]), "source": r["src"], "revenueSar": r2(rev_sar),
            "materialsSar": r2(rm_sar + pig_sar), "yerCosts": r2(yer_total),
            "sarHoldings": r2(ledger_service.bal(conn, "1102")["fc"] + max(0.0, ledger_service.bal(conn, "1201")["fc"])),
            "scenarios": scenarios}


# ---------------------------------------------------------------- 10. break-even

def break_even(conn: sqlite3.Connection, **_: Any) -> dict[str, Any]:
    s = settings_service.get(conn)
    r = production_rates(conn, s)
    fx = s["fx"]
    wages = (_avg_daily_expenses(conn, 30, ("5201",)) or DEFAULT_DAILY_WAGES) * 30
    other = (_avg_daily_expenses(conn, 30, ("5203", "6101")) or 0) * 30
    dep = dep_daily(assets_repo.list_all(conn), today()) * 30
    chill = chiller_kwh(s, 24) * 30 * s["kwhPrice"]
    fixed = wages + other + dep + chill
    mat_per = r["rm"] / r["car"] if r["car"] else s["cartonNetKg"] * 1.03
    machine_kwh_per = max(0.0, r["kwh"] - chiller_kwh(s, 24)) / (r["car"] or 1)
    var_per = (mat_per * rm_kg_cost(s) + pigment_kg_for(s, mat_per) * pig_kg_cost(s) + s["cartonCost"]
               + machine_kwh_per * s["kwhPrice"])
    price_y = s["priceSar"] * fx
    contrib = price_y - var_per
    be_month = fixed / contrib if contrib > 0 else None
    be_day = be_month / 30 if be_month is not None else None
    cap = capacity_day(s)
    points = sorted({v for v in (round((be_day or 0) * 0.5), round(be_day or 0), round(r["car"]), round(cap)) if v > 0})
    levels = [{"cartonsDay": v, "profitSar": r2((v * 30 * contrib - fixed) / fx),
               "tag": "الحالي" if v == round(r["car"]) else "القصوى" if v == round(cap) else "التعادل" if be_day and v == round(be_day) else ""}
              for v in points]
    return {"fx": fx, "source": r["src"], "priceYer": r2(price_y), "priceSar": s["priceSar"], "matPerCarton": r2(mat_per),
            "variablePerCarton": r2(var_per), "contribution": r2(contrib), "wages": r2(wages), "other": r2(other),
            "chiller": r2(chill), "depreciation": r2(dep), "fixed": r2(fixed), "breakEvenMonth": r2(be_month) if be_month else None,
            "breakEvenDay": r2(be_day) if be_day else None, "capacityDay": r2(cap),
            "capacityPct": r2(be_day / cap * 100) if be_day else None, "levels": levels}


# ---------------------------------------------------------------- 11. budget

BUDGET_LINES = [("cartons", "الإنتاج (كرتون)"), ("sold", "المبيعات (كرتون)"), ("sales", "المبيعات ر.س"),
                ("mat", "مواد وصبغة وكراتين ر.س"), ("elec", "كهرباء ر.س"), ("wages", "أجور وإعاشة ر.س"),
                ("other", "مستلزمات وإدارية ورسوم ر.س"), ("dep", "إهلاك ر.س")]
HIGHER_IS_BETTER = ("cartons", "sold", "sales", "profit")


def budget_actuals(conn: sqlite3.Connection, month: str, s: dict[str, Any]) -> dict[str, float]:
    frm, to = month + "-01", month + "-31"
    fx = s["fx"]

    def sm(**f: Any) -> float:
        return entries_repo.sums(conn, since=frm, until=to, **f)["y"]

    sales_sar = -sm(account="4101") / fx
    sold = sum((e["meta"].get("cartons") or 0) for e in entries_repo.entries_where(
        conn, ["e.src = 'sale'", "e.is_cogs = 0", "e.status = 'posted'", "e.date >= ?", "e.date <= ?"], [frm, to]))
    produced = sum(x["cartons"] or 0 for x in _approved(conn, frm, to))
    posted_dep = sm(account="5205", side="d")
    dep = posted_dep if posted_dep > 0 else -sm(account="5205", src="shift")
    a = {
        "cartons": produced, "sold": sold, "sales": sales_sar,
        "mat": -sm(accounts=("1301", "1302", "1303"), src="shift") / fx,
        "elec": (-sm(account="1401", src="shift") + sm(account="5202")) / fx,
        "wages": sm(account="5201", side="d") / fx,
        "other": sm(accounts=("5203", "5204", "6101", "6102")) / fx,
        "dep": dep / fx,
    }
    a["profit"] = a["sales"] - a["mat"] - a["elec"] - a["wages"] - a["other"] - a["dep"]
    return {k: r2(v) for k, v in a.items()}


def budget(conn: sqlite3.Connection, month: str | None = None, **_: Any) -> dict[str, Any]:
    s = settings_service.get(conn)
    month = month if month and len(month) == 7 else today()[:7]
    stored = settings_repo.get_budget(conn, month)
    actual = budget_actuals(conn, month, s)
    r = production_rates(conn, s)
    fx = s["fx"]
    suggested = {
        "cartons": round(r["car"] * 30), "sold": round(r["car"] * 30), "sales": round(r["car"] * 30 * s["priceSar"]),
        "mat": round(r["car"] * 30 * (s["cartonNetKg"] * 1.03 * rm_kg_cost(s) + s["cartonCost"]) / fx),
        "elec": round(r["kwh"] * 30 * s["kwhPrice"] / fx), "wages": round(DEFAULT_DAILY_WAGES * 30 / fx),
        "other": round(10000 * 30 / fx), "dep": round(dep_daily(assets_repo.list_all(conn), today()) * 30 / fx),
    }
    plan_profit = None
    if stored.get("sales") is not None:
        plan_profit = stored["sales"] - sum(stored.get(k) or 0 for k in ("mat", "elec", "wages", "other", "dep"))
    rows = []
    for key, label in BUDGET_LINES + [("profit", "صافي الربح التشغيلي ر.س")]:
        plan = plan_profit if key == "profit" else stored.get(key)
        diff = r2(actual[key] - plan) if plan is not None else None
        good = None if diff is None else (diff >= 0 if key in HIGHER_IS_BETTER else diff <= 0)
        rows.append({"key": key, "label": label, "plan": plan, "actual": actual[key], "diff": diff,
                     "diffPct": r2(diff / plan * 100) if diff is not None and plan else None, "good": good,
                     "suggested": suggested.get(key), "editable": key != "profit"})
    return {"month": month, "rows": rows}


def save_budget(conn: sqlite3.Connection, month: str, values: dict[str, Any]) -> dict[str, Any]:
    need(isinstance(month, str) and len(month) == 7 and month[4] == "-", "الشهر غير صحيح", "month")
    clean = {k: float(v) for k, v in (values or {}).items() if k in dict(BUDGET_LINES) and is_num(v)}
    with transaction(conn):
        settings_repo.save_budget(conn, month, clean)
    return budget(conn, month=month)


# ---------------------------------------------------------------- 12. efficiency and downtime

def efficiency(conn: sqlite3.Connection, frm: str | None = None, to: str | None = None, **_: Any) -> dict[str, Any]:
    s = settings_service.get(conn)
    frm, to = period(frm, to)
    shifts = _approved(conn, frm, to)
    cpm = cartons_per_minute(s)
    t = {"cartons": 0.0, "max": 0.0, "down": 0.0, "lostDown": 0.0, "lostOther": 0.0, "lostMargin": 0.0}
    reasons: dict[str, float] = {}
    for x in shifts:
        c = x["cost"]
        margin = s["priceSar"] - (c.get("perSar") or 0)
        t["cartons"] += x["cartons"] or 0
        t["max"] += c.get("maxCartons") or 0
        t["down"] += c.get("downMin") or 0
        t["lostDown"] += c.get("lostDown") or 0
        t["lostOther"] += c.get("lostOther") or 0
        t["lostMargin"] += ((c.get("lostDown") or 0) + (c.get("lostOther") or 0)) * margin
        if c.get("downMin"):
            key = c.get("downReason") or "بدون سبب"
            reasons[key] = reasons.get(key, 0) + c["downMin"]
    return {"from": frm, "to": to, "cartonsPerHour": r2(cpm * 60), "cycleSec": s["cycleSec"],
            "totals": {**{k: r2(v) for k, v in t.items()}, "eff": r2(t["cartons"] / t["max"] * 100) if t["max"] else None,
                       "downHours": r2(t["down"] / 60)},
            "reasons": [{"reason": k, "minutes": v, "lostCartons": r2(v * cpm)} for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])],
            "rows": [_shift_row(x, s) for x in shifts]}
