"""Accounting statements: trial balance, P&L, ledgers, cost centers, VAT, zakat, inventory."""

import sqlite3
from typing import Any

from repositories import entries_repo
from services import ledger_service, settings_service
from services.chart import ACCOUNTS, STOCK_ACCOUNTS, acc_name, acc_unit, default_cc
from utils.dates import today
from utils.errors import need
from utils.money import r2


def period(frm: str | None, to: str | None) -> tuple[str, str]:
    to = to or today()
    return frm or to[:8] + "01", to


# ---------------------------------------------------------------- 2. trial balance

def trial_balance(conn: sqlite3.Connection, to: str | None = None, **_: Any) -> dict[str, Any]:
    to = to or today()
    by_acc = {r["k"]: r for r in entries_repo.sums_by(conn, "account", until=to)}
    rows, dr, cr = [], 0.0, 0.0
    for code in ACCOUNTS:
        b = by_acc.get(code)
        if not b or abs(b["y"]) <= 0.004:
            continue
        if b["y"] > 0:
            dr += b["y"]
        else:
            cr -= b["y"]
        rows.append({"account": code, "name": acc_name(code), "debit": b["y"] if b["y"] > 0 else 0,
                     "credit": -b["y"] if b["y"] < 0 else 0, "sar": b["fc"] if ACCOUNTS[code][2] == "SAR" or code == "1201" else None,
                     "qty": b["q"] if acc_unit(code) else None, "unit": acc_unit(code)})
    return {"to": to, "rows": rows, "totals": {"debit": r2(dr), "credit": r2(cr)}, "balanced": abs(dr - cr) < 0.01}


# ---------------------------------------------------------------- 3. income statement

def income_statement(conn: sqlite3.Connection, frm: str | None = None, to: str | None = None, **_: Any) -> dict[str, Any]:
    s = settings_service.get(conn)
    frm, to = period(frm, to)
    by_acc = {r["k"]: r["y"] for r in entries_repo.sums_by(conn, "account", since=frm, until=to)}
    sales = -by_acc.get("4101", 0)
    other = -by_acc.get("4201", 0)
    cogs = by_acc.get("5101", 0)
    gross = sales - cogs
    expenses = [{"account": a, "name": acc_name(a), "amount": r2(by_acc.get(a, 0))}
                for a, v in ACCOUNTS.items() if v[1] == "X" and a != "5101" and abs(by_acc.get(a, 0)) > 0.5]
    total_exp = sum(e["amount"] for e in expenses)
    net = gross + other - total_exp
    return {"from": frm, "to": to, "fx": s["fx"], "costingStart": s["costingStart"], "sales": r2(sales), "cogs": r2(cogs),
            "gross": r2(gross), "other": r2(other), "expenses": expenses, "totalExpenses": r2(total_exp), "net": r2(net)}


# ---------------------------------------------------------------- 4 & 5. statements

def _statement(conn: sqlite3.Connection, frm: str, to: str, cur: str, show_sar: bool, **f: Any) -> dict[str, Any]:
    lines = entries_repo.lines_with_entries(conn, until=to, **f)

    def cur_ok(line: dict[str, Any]) -> bool:
        return not cur or (line.get("cur") == "SAR") == (cur == "SAR")

    def signed_fc(line: dict[str, Any]) -> float:
        return (1 if line["d"] > 0 else -1) * (line.get("fc") or 0) if line.get("cur") == "SAR" else 0

    open_y = open_fc = 0.0
    run_y = run_fc = 0.0
    rows, dr, cr = [], 0.0, 0.0
    for line in lines:
        if not cur_ok(line):
            continue
        if line["date"] < frm:
            open_y += line["d"] - line["c"]
            open_fc += signed_fc(line)
            continue
        if not rows:
            run_y, run_fc = open_y, open_fc
        run_y += line["d"] - line["c"]
        run_fc += signed_fc(line)
        dr += line["d"]
        cr += line["c"]
        rows.append({"no": line["no"], "date": line["date"], "memo": line.get("memo") or line["entry_memo"],
                     "account": line["a"], "accountName": acc_name(line["a"]), "party": line.get("party") or "",
                     "debit": line["d"], "credit": line["c"], "balance": r2(run_y),
                     "sar": r2(run_fc) if line.get("cur") == "SAR" else None, "src": line["src"], "status": line["status"]})
    if not rows:
        run_y, run_fc = open_y, open_fc
    return {"from": frm, "to": to, "cur": cur, "showSar": show_sar, "opening": {"yer": r2(open_y), "sar": r2(open_fc)},
            "rows": rows, "totals": {"debit": r2(dr), "credit": r2(cr)}, "closing": {"yer": r2(run_y), "sar": r2(run_fc)}}


def party_options(conn: sqlite3.Connection) -> list[str]:
    names = settings_service.party_names(conn)
    for acc in ("1201", "1104", "1106", "2101", "2102", "1401", "3101"):
        for p in ledger_service.parties_on(conn, acc):
            if p not in names:
                names.append(p)
    return names


def party_statement(conn: sqlite3.Connection, party: str | None = None, frm: str | None = None, to: str | None = None,
                    cur: str = "", **_: Any) -> dict[str, Any]:
    frm, to = period(frm, to)
    options = party_options(conn)
    party = party or (options[0] if options else "")
    data = _statement(conn, frm, to, cur or "", True, party=party) if party else {"rows": []}
    return {**data, "party": party, "options": options}


def account_ledger(conn: sqlite3.Connection, account: str | None = None, frm: str | None = None, to: str | None = None,
                   cur: str = "", **_: Any) -> dict[str, Any]:
    frm, to = period(frm, to)
    account = account or "1103"
    need(account in ACCOUNTS, "الحساب غير معروف", "account")
    show_sar = ACCOUNTS[account][2] == "SAR" or account == "1201"
    return {**_statement(conn, frm, to, cur or "", show_sar, account=account), "account": account, "accountName": acc_name(account)}


# ---------------------------------------------------------------- 13. cost centers

def cost_centers(conn: sqlite3.Connection, frm: str | None = None, to: str | None = None, **_: Any) -> dict[str, Any]:
    frm, to = period(frm, to)
    centers = settings_service.cost_centers(conn)
    accounts = [a for a, v in ACCOUNTS.items() if a[0] in "56" and a != "5101"]
    matrix: dict[str, dict[str, float]] = {}
    totals: dict[str, float] = {}
    for line in entries_repo.lines_with_entries(conn, since=frm, until=to, accounts=accounts):
        cc = line.get("cc") or default_cc(line["a"])
        amt = line["d"] - line["c"]
        matrix.setdefault(line["a"], {})
        matrix[line["a"]][cc] = r2(matrix[line["a"]].get(cc, 0) + amt)
        totals[cc] = r2(totals.get(cc, 0) + amt)
    rows = [{"account": a, "name": acc_name(a), "values": matrix[a], "total": r2(sum(matrix[a].values()))}
            for a in accounts if a in matrix]
    absorbed = -entries_repo.sums(conn, account="5201", src="shift", since=frm, until=to)["y"]
    return {"from": frm, "to": to, "centers": centers, "rows": rows, "totals": totals,
            "grandTotal": r2(sum(totals.values())), "absorbedLabor": r2(absorbed)}


# ---------------------------------------------------------------- 15. VAT

def vat(conn: sqlite3.Connection, frm: str | None = None, to: str | None = None, **_: Any) -> dict[str, Any]:
    s = settings_service.get(conn)
    frm, to = period(frm, to)
    out_v = -entries_repo.sums(conn, account="2301", since=frm, until=to)["y"]
    in_v = entries_repo.sums(conn, account="1402", since=frm, until=to)["y"]
    return {"from": frm, "to": to, "enabled": bool(s["vatEnabled"]), "rate": s["vatRate"], "vatNo": s["vatNo"],
            "output": r2(out_v), "input": r2(in_v), "net": r2(out_v - in_v), "fx": s["fx"]}


# ---------------------------------------------------------------- 16. zakat

def zakat_figures(conn: sqlite3.Connection, as_of: str) -> dict[str, Any]:
    s = settings_service.get(conn)

    def b(a: str) -> float:
        return ledger_service.bal(conn, a, as_of)["y"]

    def pos(x: float) -> float:
        return max(0.0, x)

    assets = [
        ("النقد في الصندوق", pos(b("1101"))),
        ("حساب المصنع – سعودي", pos(b("1102"))),
        ("حساب المصنع – يمني (إن كان موجباً)", pos(b("1103"))),
        ("العُهد لدى الموظفين", pos(b("1104"))),
        ("سلف الموظفين المرجو سدادها", pos(b("1106"))),
        ("المحافظ الإلكترونية", pos(b("1107")) + pos(b("1108")) + pos(b("1109"))),
        ("ذمم العملاء", pos(b("1201"))),
        ("مواد خام وصبغة ومفروم", pos(b("1301")) + pos(b("1302")) + pos(b("1304"))),
        ("كراتين فارغة", pos(b("1303"))),
        ("غطايا تامة", pos(b("1305"))),
    ]
    liabilities = [
        ("السحب على المكشوف (اليمني)", pos(-b("1103"))),
        ("الموردون", pos(-b("2101"))),
        ("القروض والسلف المستحقة", pos(-b("2102"))),
        ("ضرائب مستحقة", pos(-b("2301")) + pos(-b("2302"))),
    ]
    total_a = sum(v for _, v in assets)
    total_l = sum(v for _, v in liabilities)
    base = r2(total_a - total_l)
    rate = float(s.get("zakatRate") or 2.5)
    nisab = float(s.get("nisabYer") or 0)
    zakat = r2(base * rate / 100) if base > 0 and base >= nisab else 0
    return {"asOf": as_of, "assets": [{"label": l, "amount": r2(v)} for l, v in assets],
            "liabilities": [{"label": l, "amount": r2(v)} for l, v in liabilities], "totalAssets": r2(total_a),
            "totalLiabilities": r2(total_l), "base": base, "rate": rate, "nisab": nisab, "zakat": zakat, "fx": s["fx"]}


def zakat(conn: sqlite3.Connection, to: str | None = None, **_: Any) -> dict[str, Any]:
    return zakat_figures(conn, to or today())


# ---------------------------------------------------------------- 17. inventory

def inventory(conn: sqlite3.Connection, **_: Any) -> dict[str, Any]:
    rows = []
    for a in STOCK_ACCOUNTS:
        b = ledger_service.bal(conn, a)
        rows.append({"account": a, "name": acc_name(a), "qty": b["q"], "unit": acc_unit(a), "value": b["y"],
                     "avg": r2(b["y"] / b["q"]) if b["q"] > 0 else None})
    return {"rows": rows}
