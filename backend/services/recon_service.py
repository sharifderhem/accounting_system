"""Reconciliation (spec §10): consistency checks and statement matching."""

import sqlite3
from typing import Any

from database import transaction
from repositories import entries_repo, recon_repo, requests_repo, shifts_repo
from services import access, ledger_service, settings_service
from services.chart import ACCOUNTS, SOURCES, STOCK_ACCOUNTS, acc_unit
from utils.dates import days_between, is_iso, now_iso, today
from utils.errors import need
from utils.money import is_num, r2

User = dict[str, Any]
BASE_ACCOUNTS = [("1103", "حساب المصنع – يمني"), ("1102", "حساب المصنع – سعودي (بالريال السعودي)"), ("1101", "الصندوق"),
                 ("1107", "محفظة جيب"), ("1108", "محفظة إيزي"), ("1109", "محفظة فلوسك")]


def _f(x: float, d: int = 0) -> str:
    return f"{x:,.{d}f}"


# ---------------------------------------------------------------- 10.1 checks

def checks(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    s = settings_service.get(conn)
    out: list[dict[str, Any]] = []

    def add(level: str, text: str, **extra: Any) -> None:
        out.append({"level": level, "text": text, **extra})

    tb = sum(r["y"] for r in entries_repo.sums_by(conn, "account"))
    if abs(tb) < 0.01:
        add("good", "ميزان المراجعة متوازن")
    else:
        add("bad", f"ميزان المراجعة غير متوازن بفرق {_f(tb, 2)}")
    limits = s.get("creditLimits") or {}
    for p in ledger_service.parties_on(conn, "1201"):
        b = ledger_service.pbal(conn, "1201", p)
        if abs(b["fc"]) < 0.01 and abs(b["y"]) > 0.5:
            add("warn", f"{p}: رصيده بالسعودي صفر وبقي {_f(b['y'])} ر.ي فرق صرف", fxClose=p)
        elif b["fc"] < -0.5:
            add("info", f"{p}: دفع زيادة {_f(-b['fc'], 2)} ر.س (رصيد دائن له)")
        elif b["fc"] > 0.5:
            add("info", f"{p}: مستحق عليه {_f(b['fc'], 2)} ر.س — انظر تقرير المطالبة", claim=p)
        limit = float(limits.get(p) or 0)
        if limit and b["fc"] > limit:
            add("bad", f"{p}: رصيده {_f(b['fc'])} ر.س فوق سقف الائتمان {_f(limit)}")
    for p in ledger_service.parties_on(conn, "1104"):
        b = ledger_service.pbal(conn, "1104", p)
        if b["y"] > 1:
            settled = [x["date"] for x in entries_repo.lines_with_entries(conn, account="1104", party=p, side="c", live=True)]
            days = days_between(max(settled), today()) if settled else None
            add("warn", f"عهدة {p}: {_f(b['y'])} ر.ي" + (f" · آخر تصفية قبل {days} يوم" if days is not None else " · لم تُصفَّ بعد"))
    for a in STOCK_ACCOUNTS:
        q = ledger_service.bal(conn, a)["q"]
        if q < -0.001:
            add("bad", f"{ACCOUNTS[a][0]}: كمية سالبة {_f(q, 2)} {acc_unit(a)}")
    seen: dict[tuple[str, str], int] = {}
    live = entries_repo.entries_where(conn, ["e.status = 'posted'", "e.reverses_id IS NULL"], [])
    for e in live:
        if e["ref"] and e["src"] in ("sale", "in", "out") and not e["is_cogs"]:
            k = (e["src"], e["ref"])
            if k in seen:
                add("bad", f"مرجع مكرر {e['ref']} في {SOURCES[e['src']]} (القيدان {seen[k]} و {e['no']})")
            seen[k] = e["no"]
    cogs_refs = {e["ref"] for e in live if e["src"] == "sale" and e["is_cogs"]}
    for e in live:
        if e["src"] == "sale" and not e["is_cogs"] and e["date"] >= s["costingStart"] and e["ref"] not in cogs_refs:
            add("warn", f"فاتورة {e['ref'] or e['no']} بلا تكلفة مبيعات")
    pending = shifts_repo.pending_count(conn) + requests_repo.pending_requests(conn) + requests_repo.pending_advances(conn)
    if pending:
        add("warn", f"{pending} طلب أو وردية بانتظار الاعتماد")
    sar = ledger_service.bal(conn, "1102")["fc"]
    if sar < -0.01:
        limit = float(s.get("sarOdLimit") or 0)
        if not s.get("sarOverdraft"):
            add("bad", "الحساب السعودي سالب والصرّاف لا يكشف بالسعودي")
        elif limit and -sar > limit:
            add("warn", f"الحساب السعودي مكشوف بـ {_f(-sar)} ر.س، فوق حد الصرّاف {_f(limit)} ر.س")
        else:
            add("info", f"الحساب السعودي مكشوف بـ {_f(-sar)} ر.س (مسموح من الصرّاف)")
    return out


# ---------------------------------------------------------------- 10.2 statement matching

def account_options(conn: sqlite3.Connection) -> list[dict[str, str]]:
    opts = [{"key": k, "label": l} for k, l in BASE_ACCOUNTS]
    opts += [{"key": f"1104|{p}", "label": f"عهدة {p}"} for p in ledger_service.parties_on(conn, "1104")]
    return opts


def _parse_key(conn: sqlite3.Connection, key: str) -> tuple[str, str | None]:
    need(key in {o["key"] for o in account_options(conn)}, "اختر حساباً للمطابقة", "key")
    account, _, party = key.partition("|")
    return account, party or None


def _lines(conn: sqlite3.Connection, key: str) -> list[dict[str, Any]]:
    account, party = _parse_key(conn, key)
    f: dict[str, Any] = {"account": account, "live": True}
    if party:
        f["party"] = party
    out = []
    for line in entries_repo.lines_with_entries(conn, **f):
        amt = ((1 if line["d"] > 0 else -1) * (line.get("fc") or 0)) if account == "1102" else line["d"] - line["c"]
        out.append({"lineId": line["id"], "no": line["no"], "date": line["date"], "memo": line.get("memo") or line["entry_memo"],
                    "amount": r2(amt)})
    return out


def statement(conn: sqlite3.Connection, key: str) -> dict[str, Any]:
    lines = _lines(conn, key)
    marked = recon_repo.marked_lines(conn, key)
    for line in lines:
        line["cleared"] = line["lineId"] in marked
    book = r2(sum(x["amount"] for x in lines))
    cleared = r2(sum(x["amount"] for x in lines if x["cleared"]))
    return {"key": key, "options": account_options(conn), "sar": key == "1102", "lines": list(reversed(lines)),
            "book": book, "cleared": cleared, "uncleared": r2(book - cleared), "history": recon_repo.history(conn, key)}


def save(conn: sqlite3.Connection, key: str, line_ids: list[int], date: str | None, stmt: float | None, user: User) -> dict[str, Any]:
    access.require_owner(user)
    lines = _lines(conn, key)
    valid = {x["lineId"] for x in lines}
    chosen = [i for i in set(line_ids or []) if i in valid]
    if stmt is not None:
        need(is_num(stmt), "رصيد الكشف غير صحيح", "statement")
        need(is_iso(date), "اختر تاريخ الكشف", "date")
    with transaction(conn):
        recon_repo.replace_marks(conn, key, chosen)
        if stmt is not None:
            book = r2(sum(x["amount"] for x in lines))
            cleared = r2(sum(x["amount"] for x in lines if x["lineId"] in chosen))
            recon_repo.add_history(conn, key, date, float(stmt), book, cleared, r2(float(stmt) - cleared), user["label"], now_iso())
    return statement(conn, key)

