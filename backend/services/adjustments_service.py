"""Owner postings launched from reports and reconciliation:
bad-debt provision (§11.8), revaluation (§11.14), zakat accrual (§11.16), closing a
customer's FX residue (§10.1).

Each recomputes its figure on the server at the moment of posting; the amount shown
on screen is never trusted.
"""

import sqlite3
from typing import Any

from services import access, ledger_service
from services.reports import customers, statements
from utils.dates import is_iso, today
from utils.errors import DomainError, need
from utils.money import r2

User = dict[str, Any]


def post_provision(conn: sqlite3.Connection, as_of: str | None, user: User) -> dict[str, Any]:
    access.require_owner(user)
    as_of = min(as_of or today(), today())
    adj = customers.aging(conn, to=as_of)["provisionAdjust"]
    need(abs(adj) > 0.5, "المخصص مطابق؛ لا تسوية")
    lines = ([{"a": "6106", "d": adj, "cc": "sales"}, {"a": "1203", "c": adj}] if adj > 0
             else [{"a": "1203", "d": -adj}, {"a": "6106", "c": -adj, "cc": "sales"}])
    return ledger_service.post(conn, {"date": as_of, "memo": "تسوية مخصص الديون المشكوك فيها حسب أعمار الديون",
                                      "src": "manual", "lines": lines, "meta": {"provision": True}}, user)


def revalue(conn: sqlite3.Connection, user: User) -> dict[str, Any]:
    """Restate SAR balances at today's rate; the difference goes to 6103 (fc stays unchanged)."""
    access.require_owner(user)
    pos = customers.currency_position(conn)
    lines, net = [], 0.0
    for row in pos["rows"]:
        d = row["diff"]
        if abs(d) <= 0.5:
            continue
        base = {"a": row["account"], "cur": "SAR", "fc": 0}
        if row["party"]:
            base["party"] = row["party"]
        lines.append({**base, "d": d} if d > 0 else {**base, "c": -d})
        net += d
    need(lines, "لا فروق لإعادة التقييم")
    net = r2(net)
    lines.append({"a": "6103", "c": net} if net > 0 else {"a": "6103", "d": -net})
    return ledger_service.post(conn, {"date": today(), "memo": f"إعادة تقييم أرصدة الريال السعودي بسعر {pos['fx']:g}",
                                      "src": "fx", "lines": lines, "meta": {"revaluation": pos["fx"]}}, user)


def post_zakat(conn: sqlite3.Connection, as_of: str | None, user: User) -> dict[str, Any]:
    access.require_owner(user)
    as_of = as_of if is_iso(as_of) else today()
    figures = statements.zakat_figures(conn, as_of)
    need(figures["zakat"] > 0, "لا زكاة مستحقة بهذه الأرقام")
    return ledger_service.post(conn, {
        "date": min(as_of, today()), "memo": f"زكاة مستحقة عن الحول المنتهي {as_of}", "src": "manual",
        "lines": [{"a": "6105", "d": figures["zakat"]}, {"a": "2303", "c": figures["zakat"]}], "meta": {"zakat": as_of},
    }, user)


def close_fx_difference(conn: sqlite3.Connection, party: str, user: User) -> dict[str, Any]:
    """A customer owes nothing in SAR but a YER residue remains: move it to 6103."""
    access.require_owner(user)
    b = ledger_service.pbal(conn, "1201", party)
    if abs(b["fc"]) >= 0.01 or abs(b["y"]) <= 0.5:
        raise DomainError("لا يوجد فرق صرف لإقفاله لهذا العميل")
    y = b["y"]
    lines = ([{"a": "6103", "d": y}, {"a": "1201", "c": y, "party": party, "cur": "SAR", "fc": 0}] if y > 0
             else [{"a": "1201", "d": -y, "party": party, "cur": "SAR", "fc": 0}, {"a": "6103", "c": -y}])
    return ledger_service.post(conn, {"date": today(), "memo": f"إقفال فرق صرف {party}: الرصيد بالسعودي صفر",
                                      "src": "fx", "party": party, "lines": lines, "meta": {"fxClose": party}}, user)
