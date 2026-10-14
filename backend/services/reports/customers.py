"""Customer reports: claim, aging and risk, currency position (spec §10.3, §11)."""

import sqlite3
from typing import Any

from repositories import entries_repo
from services import ledger_service, settings_service
from utils.dates import add_days, days_between, today
from utils.money import r2

BUCKETS = ["0–15 يوم", "16–30", "31–60", "61–90", "أكثر من 90"]


def _bucket(days: int) -> int:
    return 0 if days <= 15 else 1 if days <= 30 else 2 if days <= 60 else 3 if days <= 90 else 4


def customers(conn: sqlite3.Connection) -> list[str]:
    names = settings_service.party_names(conn, "customer")
    for p in ledger_service.parties_on(conn, "1201"):
        if p not in names:
            names.append(p)
    return names


def open_items(conn: sqlite3.Connection, party: str, until: str | None = None) -> dict[str, Any]:
    """§10.3: payments matched to invoices oldest first, in SAR."""
    invoices, payments = [], []
    for line in entries_repo.lines_with_entries(conn, account="1201", party=party, until=until, live=True):
        if line["d"] > 0:
            sar = line.get("fc") if line.get("cur") == "SAR" else None
            invoices.append({"date": line["date"], "ref": line["ref"] or str(line["no"]), "no": line["no"],
                             "cartons": line["meta"].get("cartons") or 0, "sar": sar if sar is not None else 0, "paid": 0.0})
        elif line["c"] > 0 and line.get("cur") == "SAR" and (line.get("fc") or 0) > 0:
            payments.append({"date": line["date"], "ref": line["ref"] or str(line["no"]), "sar": line["fc"]})
    pool = sum(p["sar"] for p in payments)
    total_paid = pool
    for inv in invoices:
        applied = min(pool, inv["sar"])
        inv["paid"] = r2(applied)
        pool = r2(pool - applied)
    return {"invoices": invoices, "payments": payments, "totalPaid": r2(total_paid), "credit": r2(pool)}


# ---------------------------------------------------------------- 1. claim

def claim(conn: sqlite3.Connection, party: str | None = None, to: str | None = None, **_: Any) -> dict[str, Any]:
    s = settings_service.get(conn)
    to = to or today()
    options = customers(conn)
    party = party or (options[0] if options else "")
    o = open_items(conn, party, to) if party else {"invoices": [], "payments": [], "totalPaid": 0, "credit": 0}
    open_ = [{**i, "remaining": r2(i["sar"] - i["paid"]), "age": max(0, days_between(i["date"], to))}
             for i in o["invoices"] if i["sar"] - i["paid"] > 0.004]
    due = r2(sum(i["remaining"] for i in open_))
    return {"party": party, "options": options, "to": to, "fx": s["fx"],
            "totalInvoiced": r2(sum(i["sar"] for i in o["invoices"])), "totalPaid": o["totalPaid"],
            "credit": o["credit"], "due": due, "open": open_, "payments": o["payments"]}


# ---------------------------------------------------------------- 8. aging and risk

def aging(conn: sqlite3.Connection, to: str | None = None, **_: Any) -> dict[str, Any]:
    s = settings_service.get(conn)
    to = to or today()
    pct = s.get("provPct") or [0, 0, 10, 25, 50]
    limits = s.get("creditLimits") or {}
    rows, totals, need_prov = [], [0.0] * 5, 0.0
    for c in customers(conn):
        buckets = [0.0] * 5
        for inv in open_items(conn, c, to)["invoices"]:
            rem = inv["sar"] - inv["paid"]
            if rem > 0.004:
                k = _bucket(days_between(inv["date"], to))
                buckets[k] += rem
                totals[k] += rem
        due = sum(buckets)
        need_prov += sum(v * (pct[k] or 0) / 100 for k, v in enumerate(buckets))
        limit = float(limits.get(c) or 0)
        rows.append({"party": c, "buckets": [r2(v) for v in buckets], "due": r2(due), "limit": limit or None,
                     "usedPct": r2(due / limit * 100) if limit else None})
    since = add_days(to, -30)
    sales: dict[str, float] = {}
    for line in entries_repo.lines_with_entries(conn, account="1201", src="sale", live=True, not_cogs=True, until=to):
        if line["date"] > since and line["d"] > 0:
            sales[line.get("party") or ""] = sales.get(line.get("party") or "", 0) + (line.get("fc") or 0)
    total_sales = sum(sales.values())
    concentration = [{"party": p, "sar": r2(v), "share": r2(v / total_sales * 100) if total_sales else 0}
                     for p, v in sorted(sales.items(), key=lambda kv: -kv[1])]
    needed = r2(need_prov * s["fx"])
    recorded = r2(-ledger_service.bal(conn, "1203")["y"])
    return {"to": to, "buckets": BUCKETS, "rows": rows, "totals": [r2(v) for v in totals], "totalDue": r2(sum(totals)),
            "provPct": pct, "provisionNeeded": needed, "provisionRecorded": recorded, "provisionAdjust": r2(needed - recorded),
            "concentration": concentration, "fx": s["fx"]}


# ---------------------------------------------------------------- 14. currency position

def currency_position(conn: sqlite3.Connection, **_: Any) -> dict[str, Any]:
    s = settings_service.get(conn)
    items = [("حساب المصنع – سعودي", "1102", None, ledger_service.bal(conn, "1102"))]
    for p in ledger_service.parties_on(conn, "1201"):
        b = ledger_service.pbal(conn, "1201", p)
        if abs(b["fc"]) > 0.01:
            items.append((f"ذمة {p}", "1201", p, b))
    rows = []
    for label, acc, party, b in items:
        now = r2(b["fc"] * s["fx"])
        rows.append({"label": label, "account": acc, "party": party, "sar": b["fc"], "bookYer": b["y"],
                     "avgRate": r2(b["y"] / b["fc"]) if b["fc"] else None, "nowYer": now, "diff": r2(now - b["y"])})
    return {"fx": s["fx"], "rows": rows, "totalDiff": r2(sum(r["diff"] for r in rows))}
