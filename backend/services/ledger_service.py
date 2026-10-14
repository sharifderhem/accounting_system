"""The posting engine (spec §1): balanced, immutable, numbered, attributable entries.

Every write to the books goes through ``post`` or ``reverse``. Both run inside a
write transaction, so the entry number is unique and gap-free and a failure
leaves nothing behind.
"""

import sqlite3
from typing import Any

from database import transaction
from repositories import assets_repo, entries_repo, shifts_repo
from services import settings_service
from services.chart import ACCOUNTS, SOURCES
from services.costing import with_labor_delta
from utils.dates import now_iso, today
from utils.errors import Conflict, DomainError, NotFound
from utils.money import is_num, r2

Line = dict[str, Any]
Entry = dict[str, Any]

_LINE_KEYS = ("a", "d", "c", "party", "cur", "fc", "qty", "shift", "cc", "asset", "memo")
REF_CHECKED_SOURCES = ("sale", "in", "out")


def clean_lines(lines: list[Line]) -> list[Line]:
    """Round to 2 decimals, drop empty lines and empty optional fields (as the prototype did)."""
    out = []
    for raw in lines:
        line = {k: raw[k] for k in _LINE_KEYS if k in raw and raw[k] not in (None, "")}
        line["d"], line["c"] = r2(line.get("d") or 0), r2(line.get("c") or 0)
        if line["d"] <= 0.004 and line["c"] <= 0.004:
            continue
        if "fc" in line:
            line["fc"] = r2(line["fc"])
        out.append(line)
    return out


def validate(conn: sqlite3.Connection, entry: Entry, check_ref: bool = True) -> Entry:
    """Apply every §1 rule to a proposed entry. Returns the cleaned entry."""
    s = settings_service.get(conn)
    entry = {**entry, "lines": clean_lines(entry.get("lines") or [])}
    lines = entry["lines"]
    if not lines:
        raise DomainError("القيد فارغ")
    if entry.get("src") not in SOURCES:
        raise DomainError("نوع القيد غير معروف")
    for line in lines:
        if line["a"] not in ACCOUNTS:
            raise DomainError(f"حساب غير معروف: {line['a']}")
        if not (is_num(line["d"]) and is_num(line["c"])) or line["d"] < 0 or line["c"] < 0:
            raise DomainError("المبالغ يجب أن تكون موجبة")
        if line["d"] > 0 and line["c"] > 0:
            raise DomainError("السطر الواحد إما مدين أو دائن")
        if ACCOUNTS[line["a"]][2] == "SAR" and line.get("cur") != "SAR":
            raise DomainError("سطر الحساب السعودي يجب أن يحمل المبلغ بالريال السعودي")
        if line.get("qty") is not None and (not is_num(line["qty"]) or line["qty"] < 0):
            raise DomainError("الكمية غير صحيحة")
    d = r2(sum(line["d"] for line in lines))
    c = r2(sum(line["c"] for line in lines))
    if abs(d - c) > 0.01:
        raise DomainError(f"القيد غير متوازن: مدين {d:,.2f} ودائن {c:,.2f}")
    date = entry.get("date") or ""
    if len(date) != 10:
        raise DomainError("اختر التاريخ")
    lock = s.get("lockDate") or ""
    if lock and date <= lock:
        raise DomainError(f"الفترة مقفلة حتى {lock}. سجّل الحركة بتاريخ لاحق أو افتح الفترة من الإعدادات.")
    ref = str(entry.get("ref") or "")
    if check_ref and ref and entry["src"] in REF_CHECKED_SOURCES and not entry.get("is_cogs") and not entry.get("reverses_id"):
        dup = entries_repo.find_ref(conn, entry["src"], ref)
        if dup:
            raise Conflict(f"المرجع {ref} مسجل مسبقاً في {SOURCES[entry['src']]} (القيد {dup})", "ref")
    return entry


def post(conn: sqlite3.Connection, entry: Entry, user: dict[str, Any], approver: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate and post one entry. Returns {id, no}."""
    with transaction(conn):
        entry = validate(conn, entry)
        entry["created_by"] = entry.get("created_by") or user["id"]
        entry["created_by_label"] = entry.get("created_by_label") or user["label"]
        if approver:
            entry["approved_by"], entry["approved_by_label"] = approver["id"], approver["label"]
        no = entries_repo.next_no(conn)
        entry_id = entries_repo.insert_entry(conn, entry, no, now_iso())
    return {"id": entry_id, "no": no}


def post_many(conn: sqlite3.Connection, entries: list[Entry], user: dict[str, Any], approver: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Post several entries as one action: all succeed or none do."""
    with transaction(conn):
        return [post(conn, e, user, approver) for e in entries]


def reverse(conn: sqlite3.Connection, entry_id: int, user: dict[str, Any]) -> dict[str, Any]:
    """§5.10: mirror entry dated today; the original is marked reversed.

    Blocked when either today or the original's date falls in the locked period, so a
    closed month never changes.
    """
    with transaction(conn):
        e = entries_repo.get(conn, entry_id)
        if not e:
            raise NotFound("القيد غير موجود")
        if e["status"] == "reversed":
            raise Conflict("القيد معكوس مسبقاً")
        if e["reverses_id"]:
            raise DomainError("لا يُعكس القيد العكسي. سجّل الحركة الصحيحة من جديد.")
        lock = settings_service.get(conn).get("lockDate") or ""
        if lock and e["date"] <= lock:
            raise DomainError(f"القيد بتاريخ {e['date']} داخل فترة مقفلة حتى {lock}")
        lines = []
        for line in e["lines"]:
            mirrored = {k: v for k, v in line.items() if k not in ("id", "d", "c")}
            mirrored["d"], mirrored["c"] = line["c"], line["d"]
            lines.append(mirrored)
        res = post(conn, {
            "date": today(), "memo": f"عكس القيد {e['no']}: {e['memo']}", "src": "rev", "ref": str(e["no"]),
            "party": e["party"], "reverses_id": e["id"], "meta": {"reverses": e["id"], "reversesNo": e["no"]}, "lines": lines,
        }, user)
        entries_repo.mark_reversed(conn, e["id"], res["id"])
        _undo_side_effects(conn, e)
    return res


def _undo_side_effects(conn: sqlite3.Connection, e: Entry) -> None:
    meta = e.get("meta") or {}
    if e["src"] == "shift":
        shifts_repo.reset_by_entry(conn, e["id"])
    if meta.get("lateLabor"):
        approved = shifts_repo.approved_for(conn, meta["date"], meta["shift"])
        amount = sum(line["d"] for line in e["lines"] if line["a"] == "1305")
        if approved and approved.get("cost"):
            cost = with_labor_delta(approved["cost"], approved["cartons"], -amount, settings_service.get(conn))
            shifts_repo.update_cost(conn, approved["id"], cost)
    if meta.get("assetAcquired"):
        asset = assets_repo.get(conn, meta["assetAcquired"])
        if asset:
            assets_repo.update(conn, asset["id"], cost=0, amount=0, posted_to=None)
    for item in meta.get("depreciation") or []:
        asset = assets_repo.get(conn, item["asset"])
        if asset and asset["posted_to"] == item["to"]:
            assets_repo.update(conn, asset["id"], posted_to=item["prev"])


# ---- balances ----

def bal(conn: sqlite3.Connection, account: str, until: str | None = None) -> dict[str, float]:
    return entries_repo.sums(conn, account=account, until=until)


def pbal(conn: sqlite3.Connection, account: str, party: str, until: str | None = None) -> dict[str, float]:
    return entries_repo.sums(conn, account=account, party=party, until=until)


def avg_cost(conn: sqlite3.Connection, account: str, fallback: float | None, until: str | None = None) -> float | None:
    """Weighted-average unit cost of a stock account as of a date (§1.5)."""
    b = bal(conn, account, until)
    return b["y"] / b["q"] if b["q"] > 0.0001 and b["y"] > 0 else fallback


def parties_on(conn: sqlite3.Connection, account: str) -> list[str]:
    return entries_repo.parties_on(conn, account)
