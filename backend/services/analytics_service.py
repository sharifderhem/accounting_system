"""Analytics (spec §12.2): period comparison, drivers, cost bridge, daily series, shift comparison."""

import sqlite3
from typing import Any

from repositories import entries_repo, shifts_repo
from services import settings_service
from services.costing import capacity_day
from utils.dates import add_days, today
from utils.money import r2

COMPONENTS = [("rm", "المواد الخام", "rmCost"), ("pig", "الصبغة", "pigCost"), ("ct", "الكراتين", "ctCost"),
              ("el", "الكهرباء", "elec"), ("lab", "الأجور والإعاشة", "labor"), ("dep", "الإهلاك", "dep")]
PETTY = ("5203", "5204", "6101", "6102")
PERIODS = {"day": 1, "week": 7, "month": 30}


def _last_active(conn: sqlite3.Connection) -> str:
    t = today()
    candidates = [entries_repo.last_activity_date(conn, t)]
    candidates += [x["date"] for x in shifts_repo.list_all(conn, until=t, limit=1)]
    candidates = [c for c in candidates if c]
    return max(candidates) if candidates else t


def _empty_day(d: str) -> dict[str, Any]:
    return {"d": d, "wages": 0.0, "petty": 0.0, "cartons": 0.0, "max": 0.0, "kwh": 0.0, "down": 0.0, "shifts": 0,
            "cost": 0.0, "comp": {k: 0.0 for k, _, _ in COMPONENTS}}


def daily_data(conn: sqlite3.Connection, days: list[str]) -> list[dict[str, Any]]:
    by_day = {d: _empty_day(d) for d in days}
    for line in entries_repo.lines_with_entries(conn, since=days[0], until=days[-1], live=True, side="d",
                                                accounts=("5201",) + PETTY):
        meta = line["meta"]
        if line["src"] == "shift" or meta.get("depreciation") or meta.get("reclass"):
            continue
        day = by_day.get(line["date"])
        if day is None:
            continue
        if line["a"] == "5201":
            day["wages"] += line["d"]
        else:
            day["petty"] += line["d"]
    for x in shifts_repo.list_all(conn, status="approved", since=days[0], until=days[-1]):
        day, c = by_day.get(x["date"]), x.get("cost") or {}
        if day is None or not c:
            continue
        day["cartons"] += x["cartons"] or 0
        day["max"] += c.get("maxCartons") or 0
        day["kwh"] += c.get("kwh") or 0
        day["down"] += c.get("downMin") or 0
        day["shifts"] += 1
        day["cost"] += c.get("total") or 0
        for key, _, field in COMPONENTS:
            day["comp"][key] += c.get(field) or 0
    return [by_day[d] for d in days]


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out = _empty_day("")
    out["days"] = len(rows)
    for r in rows:
        for k in ("wages", "petty", "cartons", "max", "kwh", "down", "shifts", "cost"):
            out[k] += r[k]
        for k in out["comp"]:
            out["comp"][k] += r["comp"][k]
    return out


def _f(x: float, d: int = 0) -> str:
    return f"{x:,.{d}f}"


def drivers(a: dict[str, Any], b: dict[str, Any], fx: float) -> list[dict[str, Any]]:
    """Plain-language lines on what improved (إيجابي) and what got worse (سلبي)."""
    out: list[dict[str, Any]] = []

    def add(good: bool, title: str, text: str) -> None:
        out.append({"good": good, "title": title, "text": text})

    def per(o: dict[str, Any], k: str) -> float | None:
        return o["comp"][k] / o["cartons"] if o["cartons"] else None

    prod_a = a["cartons"] / a["days"] if a["days"] else 0
    prod_b = b["cartons"] / b["days"] if b["days"] else 0
    if a["cartons"] and b["cartons"]:
        eff_a, eff_b = a["cartons"] / a["max"] if a["max"] else 0, b["cartons"] / b["max"] if b["max"] else 0
        sh_a, sh_b = a["shifts"] / a["days"], b["shifts"] / b["days"]
        dm_a = a["down"] / a["shifts"] if a["shifts"] else 0
        dm_b = b["down"] / b["shifts"] if b["shifts"] else 0
        add(prod_b >= prod_a, "الإنتاج اليومي", f"من {_f(prod_a, 1)} إلى {_f(prod_b, 1)} كرتون ({_f((prod_b - prod_a) / prod_a * 100, 1)}%)")
        if abs(sh_b - sh_a) > 0.05:
            add(sh_b > sh_a, "عدد الورديات", f"من {_f(sh_a, 1)} إلى {_f(sh_b, 1)} وردية يومياً")
        if abs(dm_b - dm_a) >= 5:
            add(dm_b < dm_a, "التوقف", f"من {_f(dm_a)} إلى {_f(dm_b)} دقيقة في الوردية")
        if abs(eff_b - eff_a) > 0.01:
            add(eff_b > eff_a, "الكفاءة", f"من {_f(eff_a * 100)}% إلى {_f(eff_b * 100)}% من الطاقة القصوى")
        for key, name, _ in COMPONENTS:
            pa, pb = per(a, key), per(b, key)
            if pa is not None and pb is not None and abs(pb - pa) >= fx * 0.25:
                sign = "+" if pb > pa else ""
                add(pb < pa, f"{name} للكرتون", f"من {_f(pa)} إلى {_f(pb)} ر.ي ({sign}{_f((pb - pa) / fx, 2)} ر.س)")
        ka, kb = a["kwh"] / a["cartons"], b["kwh"] / b["cartons"]
        if abs(kb - ka) > 0.2:
            note = " (زيادة الإنتاج وزّعت تشغيل المبرد الثابت على كراتين أكثر)" if kb < ka and prod_b > prod_a else ""
            add(kb < ka, "الطاقة للكرتون", f"من {_f(ka, 1)} إلى {_f(kb, 1)} ك.و{note}")
    elif b["cartons"] and not a["cartons"]:
        add(True, "الإنتاج", "بدأ تسجيل الإنتاج في هذه الفترة")
    ea = (a["wages"] + a["petty"]) / (a["days"] or 1)
    eb = (b["wages"] + b["petty"]) / (b["days"] or 1)
    if ea or eb:
        add(eb <= ea, "المصروفات اليومية",
            f"من {_f(ea)} إلى {_f(eb)} ر.ي (أجور من {_f(a['wages'] / (a['days'] or 1))} إلى {_f(b['wages'] / (b['days'] or 1))} · "
            f"نثريات من {_f(a['petty'] / (a['days'] or 1))} إلى {_f(b['petty'] / (b['days'] or 1))})")
    return out


def _shift_side(conn: sqlite3.Connection, s: dict[str, Any], name: str, since: str, until: str) -> dict[str, Any]:
    items = [x for x in shifts_repo.list_all(conn, status="approved", since=since, until=until) if x["shift"] == name and x.get("cost")]
    if not items:
        return {"n": 0, "eff": None, "down": None, "kwh": None, "cost": None}
    c = sum(x["cartons"] or 0 for x in items)
    m = sum(x["cost"].get("maxCartons") or 0 for x in items)
    dn = sum(x["cost"].get("downMin") or 0 for x in items)
    k = sum(x["cost"].get("kwh") or 0 for x in items)
    t = sum(x["cost"].get("total") or 0 for x in items)
    return {"n": len(items), "eff": r2(c / m * 100) if m else None, "down": r2(dn / (len(items) * s["shiftHours"] * 60) * 100),
            "kwh": r2(k / c) if c else None, "cost": r2(t / c / s["fx"]) if c else None}


def overview(conn: sqlite3.Connection, period: str = "week") -> dict[str, Any]:
    s = settings_service.get(conn)
    fx = s["fx"]
    period = period if period in PERIODS else "week"
    span = PERIODS[period]
    end = _last_active(conn)
    n = max(30, span * 2)
    days = [add_days(end, -i) for i in range(n - 1, -1, -1)]
    rows = daily_data(conn, days)
    cur, prev = aggregate(rows[-span:]), aggregate(rows[-span * 2:-span])

    def per_c(o):
        return o["cost"] / o["cartons"] / fx if o["cartons"] else None

    def kwh_c(o):
        return o["kwh"] / o["cartons"] if o["cartons"] else None

    def eff(o):
        return o["cartons"] / o["max"] * 100 if o["max"] else None

    def down(o):
        return o["down"] / (o["shifts"] * s["shiftHours"] * 60) * 100 if o["shifts"] else None

    def daily_prod(o):
        return o["cartons"] / o["days"] if o["days"] and o["cartons"] else None

    def daily_exp(o):
        v = (o["wages"] + o["petty"]) / (o["days"] or 1)
        return v or None

    tiles = [
        {"key": "production", "label": "الإنتاج اليومي", "unit": "كرتون", "better": "high", "digits": 1, "cur": daily_prod(cur), "prev": daily_prod(prev)},
        {"key": "cost", "label": "تكلفة الكرتون", "unit": "ر.س", "better": "low", "digits": 1, "cur": per_c(cur), "prev": per_c(prev)},
        {"key": "kwh", "label": "الطاقة للكرتون", "unit": "ك.و", "better": "low", "digits": 1, "cur": kwh_c(cur), "prev": kwh_c(prev)},
        {"key": "eff", "label": "الكفاءة", "unit": "%", "better": "high", "digits": 0, "cur": eff(cur), "prev": eff(prev)},
        {"key": "down", "label": "نسبة التوقف", "unit": "%", "better": "low", "digits": 1, "cur": down(cur), "prev": down(prev)},
        {"key": "expenses", "label": "المصروفات والنثريات يومياً", "unit": "ر.ي", "better": "low", "digits": 0, "cur": daily_exp(cur), "prev": daily_exp(prev)},
    ]
    for t in tiles:
        t["cur"] = r2(t["cur"]) if t["cur"] is not None else None
        t["prev"] = r2(t["prev"]) if t["prev"] is not None else None
        t["changePct"] = r2((t["cur"] - t["prev"]) / abs(t["prev"]) * 100) if t["cur"] is not None and t["prev"] else None

    bridge = None
    if prev["cartons"] and cur["cartons"]:
        deltas = [{"label": name, "value": r2((cur["comp"][k] / cur["cartons"] - prev["comp"][k] / prev["cartons"]) / fx)}
                  for k, name, _ in COMPONENTS]
        bridge = {"previous": r2(prev["cost"] / prev["cartons"] / fx), "current": r2(cur["cost"] / cur["cartons"] / fx),
                  "deltas": [d for d in deltas if abs(d["value"]) >= 0.005]}

    first = next((i for i, r in enumerate(rows) if r["wages"] or r["petty"] or r["cartons"]), None)
    start = len(rows) - 7 if first is None else min(len(rows) - 7, max(len(rows) - 30, first))
    chart = [{"d": r["d"], "wages": r2(r["wages"]), "petty": r2(r["petty"]), "cartons": r["cartons"], "kwh": r2(r["kwh"]),
              "kwhPer": r2(r["kwh"] / r["cartons"]) if r["cartons"] else None} for r in rows[start:]]

    window = rows[-span:]
    morning = _shift_side(conn, s, "صباحية", window[0]["d"], window[-1]["d"])
    evening = _shift_side(conn, s, "مسائية", window[0]["d"], window[-1]["d"])

    return {"period": period, "end": end, "span": span, "tiles": tiles, "drivers": drivers(prev, cur, fx), "bridge": bridge,
            "chart": chart, "capacityDay": r2(capacity_day(s)), "chillerKw": s["chillerKw"], "chillerLoad": s["chillerLoad"],
            "shifts": {"morning": morning, "evening": evening}}
