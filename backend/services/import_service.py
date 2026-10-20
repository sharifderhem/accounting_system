"""One-time copy of the claude.ai prototype's books into this database (spec §17, IMPORT_SPEC.md).

This is a copy, not a re-posting: entries keep their numbers, dates, amounts and status, and none of
the posting rules (lock date, duplicate references, SAR overdraft, dual control, costing) run. The
whole import is one transaction, verified against the figures shipped in the export before commit.
"""

import hashlib
import json
import logging
import math
import sqlite3
from typing import Any

from database import fetch_one, transaction
from repositories import assets_repo, entries_repo, import_repo, settings_repo
from services.chart import ACCOUNTS, PARTY_TYPES, SHIFTS
from utils.dates import is_iso, now_iso
from utils.errors import Conflict, Unprocessable
from utils.money import r2

logger = logging.getLogger(__name__)

TOL = 0.01
LINE_FIELDS = ("a", "d", "c", "party", "cur", "fc", "qty", "shift", "cc", "asset", "prod", "memo")
PARTY_ACCOUNTS = ("1104", "1106", "1201", "2101", "2102", "2104", "3101")
BY_LABELS = {"seed": "إدخال افتتاحي (النموذج الأولي)", "claude": "المساعد (النموذج الأولي)"}
REQUEST_KINDS = ("out", "exp", "fx")


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _bad(message: str, field: str) -> Unprocessable:
    return Unprocessable(message, field)


# ---------------------------------------------------------------- validation (before any write)

def _validate(p: dict[str, Any]) -> None:
    if not isinstance(p.get("settings", {}), dict):
        raise _bad("settings يجب أن يكون كائناً", "settings")
    for i, party in enumerate((p.get("settings") or {}).get("parties") or []):
        if not isinstance(party, dict) or not str(party.get("name") or "").strip() or party.get("type") not in PARTY_TYPES:
            raise _bad("طرف غير صحيح", f"settings.parties[{i}]")

    asset_ids = set()
    for i, a in enumerate(p.get("assets") or []):
        f = f"assets[{i}]"
        if not isinstance(a, dict) or not isinstance(a.get("id"), str) or not a["id"]:
            raise _bad("أصل بلا معرّف", f)
        if a["id"] in asset_ids:
            raise _bad(f"معرّف أصل مكرر: {a['id']}", f + ".id")
        asset_ids.add(a["id"])
        if not is_iso(a.get("date")):
            raise _bad("تاريخ غير صحيح", f + ".date")
        if not (_num(a.get("life")) and a["life"] > 0):
            raise _bad("العمر الإنتاجي غير صحيح", f + ".life")
        for k in ("cost", "amount", "salvage"):
            if a.get(k) is not None and not _num(a[k]):
                raise _bad("قيمة غير صحيحة", f"{f}.{k}")

    entries = p.get("entries")
    if not isinstance(entries, list) or not entries:
        raise _bad("لا توجد قيود في الملف", "entries")
    nos, ids, tb = set(), set(), 0.0
    for i, e in enumerate(entries):
        f = f"entries[{i}]"
        if not isinstance(e, dict):
            raise _bad("قيد غير صحيح", f)
        no = e.get("no")
        if not (isinstance(no, int) and not isinstance(no, bool) and no > 0):
            raise _bad("رقم القيد يجب أن يكون عدداً صحيحاً موجباً", f + ".no")
        if no in nos:
            raise _bad(f"رقم قيد مكرر: {no}", f + ".no")
        nos.add(no)
        if not isinstance(e.get("id"), str) or not e["id"] or e["id"] in ids:
            raise _bad("معرّف القيد مفقود أو مكرر", f + ".id")
        ids.add(e["id"])
        if not is_iso(e.get("date")):
            raise _bad("التاريخ يجب أن يكون YYYY-MM-DD", f + ".date")
        if e.get("status", "posted") not in ("posted", "reversed"):
            raise _bad("حالة القيد غير معروفة", f + ".status")
        if not isinstance(e.get("src"), str) or not e["src"]:
            raise _bad("نوع القيد مفقود", f + ".src")
        if e.get("meta") is not None and not isinstance(e["meta"], dict):
            raise _bad("meta يجب أن يكون كائناً", f + ".meta")
        lines = e.get("lines")
        if not isinstance(lines, list) or not lines:
            raise _bad("القيد بلا أسطر", f + ".lines")
        d_sum = c_sum = 0.0
        for j, line in enumerate(lines):
            lf = f"{f}.lines[{j}]"
            if not isinstance(line, dict):
                raise _bad("سطر غير صحيح", lf)
            if line.get("a") not in ACCOUNTS:
                raise _bad(f"حساب غير معروف: {line.get('a')}", lf + ".a")
            d, c = line.get("d", 0) or 0, line.get("c", 0) or 0
            if not (_num(d) and _num(c)) or d < 0 or c < 0:
                raise _bad("المبالغ يجب أن تكون أرقاماً موجبة", lf)
            if (d > 0) == (c > 0):
                raise _bad("السطر يجب أن يكون مديناً أو دائناً فقط", lf)
            if line.get("cur") == "SAR" and not _num(line.get("fc")):
                raise _bad("سطر بالريال السعودي بلا fc", lf + ".fc")
            if line.get("qty") is not None and not _num(line["qty"]):
                raise _bad("الكمية غير صحيحة", lf + ".qty")
            d_sum += d
            c_sum += c
        if abs(d_sum - c_sum) > TOL:
            raise _bad(f"القيد {no} غير متوازن: مدين {d_sum:,.2f} ودائن {c_sum:,.2f}", f)
        if e.get("status", "posted") != "reversed" and not e.get("reversal"):
            tb += d_sum - c_sum
    for i, e in enumerate(entries):
        if e.get("reversal") and (e.get("meta") or {}).get("reverses") not in ids:
            raise _bad("قيد عكسي لا يشير إلى قيد موجود", f"entries[{i}].meta.reverses")
    expected_tb = (p.get("expected") or {}).get("trialBalance", 0)
    if abs(r2(tb) - (expected_tb or 0)) > TOL:
        raise _bad(f"ميزان المراجعة في الملف لا يساوي {expected_tb}: الفرق {tb:,.2f}", "entries")

    entry_ids = {e["id"] for e in entries}
    slots = set()
    for i, s in enumerate(p.get("shifts") or []):
        f = f"shifts[{i}]"
        if not isinstance(s, dict) or not is_iso(s.get("date")):
            raise _bad("تاريخ الوردية غير صحيح", f + ".date")
        if s.get("shift") not in SHIFTS:
            raise _bad("اسم الوردية غير معروف", f + ".shift")
        if s.get("status", "pending") not in ("pending", "approved", "rejected"):
            raise _bad("حالة الوردية غير معروفة", f + ".status")
        if s.get("status") == "approved" and s.get("entryId") not in entry_ids:
            raise _bad("وردية معتمدة بلا قيد إنتاج موجود", f + ".entryId")
        if s.get("status") != "rejected":
            if (s["date"], s["shift"]) in slots:
                raise _bad("ورديتان لنفس التاريخ والفترة", f)
            slots.add((s["date"], s["shift"]))

    for i, r in enumerate(p.get("requests") or []):
        if not isinstance(r, dict) or r.get("kind") not in REQUEST_KINDS or not isinstance(r.get("entries"), list):
            raise _bad("طلب صرف غير صحيح", f"requests[{i}]")
    for i, a in enumerate(p.get("advances") or []):
        if not isinstance(a, dict) or not str(a.get("employee") or "").strip() or not _num(a.get("amount")):
            raise _bad("طلب سلفة غير صحيح", f"advances[{i}]")
    for i, b in enumerate(p.get("budgets") or []):
        month = (b or {}).get("month") if isinstance(b, dict) else None
        if not (isinstance(month, str) and len(month) == 7 and month[4] == "-"):
            raise _bad("شهر الموازنة غير صحيح", f"budgets[{i}].month")


# ---------------------------------------------------------------- writes

def _owner(conn: sqlite3.Connection) -> dict[str, Any]:
    row = fetch_one(conn, "SELECT id, label FROM users WHERE role = 'owner' AND active = 1 ORDER BY id LIMIT 1")
    if not row:
        raise Unprocessable("أنشئ حساب المالك أولاً ثم أعد الاستيراد")
    return row


def _by_label(by: Any, owner: dict[str, Any]) -> str:
    if by == "owner":
        return owner["label"]
    return BY_LABELS.get(by, "مستخدم في النموذج الأولي")


def _line(raw: dict[str, Any]) -> dict[str, Any]:
    line = {k: raw[k] for k in LINE_FIELDS if k in raw and raw[k] is not None}
    line["d"], line["c"] = raw.get("d") or 0, raw.get("c") or 0
    extra = {k: v for k, v in raw.items() if k not in LINE_FIELDS}
    if extra:
        line["extra"] = extra
    return line


def _is_cogs(e: dict[str, Any]) -> bool:
    accounts = {line["a"] for line in e["lines"]}
    return e["src"] == "sale" and "5101" in accounts and "4101" not in accounts


def _write(conn: sqlite3.Connection, p: dict[str, Any], owner: dict[str, Any]) -> dict[str, int]:
    settings = dict(p.get("settings") or {})
    parties = settings.pop("parties", None) or []
    if settings:
        settings_repo.save(conn, settings)
    for party in parties:
        import_repo.upsert_party(conn, party["name"].strip(), party["type"])

    for a in p.get("assets") or []:
        assets_repo.insert(conn, {
            "id": a["id"], "name": a.get("name") or a["id"], "date": a["date"], "cost": a.get("cost") or 0,
            "amount": a.get("amount") or 0, "cur": a.get("cur") or "YER", "life": a["life"], "salvage": a.get("salvage") or 0,
            "cc": a.get("cc") or "prod", "note": a.get("note") or "", "posted_to": a.get("postedTo"),
            "created_at": now_iso(),
        })

    entries = sorted(p["entries"], key=lambda e: e["no"])
    for e in entries:
        meta = e.get("meta") or {}
        entries_repo.insert_entry(conn, {
            "date": e["date"], "memo": e.get("memo") or "", "src": e["src"], "ref": str(e.get("ref") or ""),
            "party": e.get("party") or "", "status": e.get("status") or "posted", "is_cogs": _is_cogs(e),
            "created_by": owner["id"], "created_by_label": _by_label(e.get("by"), owner),
            "approved_by_label": meta.get("checker") or "", "meta": meta, "legacy_id": e["id"],
            "legacy_by": str(e.get("by") or ""), "lines": [_line(line) for line in e["lines"]],
        }, e["no"], e.get("at") or now_iso())

    by_legacy = import_repo.entry_ids_by_legacy(conn)
    for e in entries:
        if e.get("reversal"):
            mirror, original = by_legacy[e["id"]], by_legacy[e["meta"]["reverses"]]
            conn.execute("UPDATE entries SET reverses_id = ? WHERE id = ?", (original, mirror))
            entries_repo.set_reversed_by(conn, original, mirror)

    for s in p.get("shifts") or []:
        import_repo.insert_shift(conn, {
            "date": s["date"], "shift": s["shift"], "by_name": s.get("byName") or "",
            "meter_start": s.get("meterStart") or 0, "meter_end": s.get("meterEnd") or 0, "bags": s.get("bags") or 0,
            "extra_kg": s.get("regrindKg") or 0, "cartons": s.get("cartons") or 0, "scrap_kg": s.get("scrapKg") or 0,
            "shots_start": s.get("shotsStart"), "shots_end": s.get("shotsEnd"), "down_min": s.get("downMin") or 0,
            "down_reason": s.get("downReason") or "", "notes": s.get("notes") or "", "status": s.get("status") or "pending",
            "entry_id": by_legacy.get(s.get("entryId")) if s.get("status") == "approved" else None,
            "cost": s.get("cost") if s.get("status") == "approved" else None, "created_by": owner["id"],
            "created_at": s.get("at") or now_iso(), "decided_by": owner["id"] if s.get("status") in ("approved", "rejected") else None,
            "decided_at": s.get("approvedAt"), "legacy_id": s.get("id"), "doc": s,
        })

    for r in p.get("requests") or []:
        status = r.get("status") or "pending"
        if status == "rejected" and "سحب" in str(r.get("note") or ""):
            status = "withdrawn"
        if status not in ("pending", "approved", "rejected", "withdrawn"):
            status = "rejected"
        import_repo.insert_request(conn, {
            "kind": r["kind"], "entries": r["entries"], "summary": r.get("summary") or "", "amount": r.get("amount") or 0,
            "status": status, "created_by": owner["id"], "created_by_label": r.get("createdByLabel") or "",
            "created_at": r.get("at") or now_iso(), "decided_by": owner["id"] if status != "pending" else None,
            "decided_by_label": r.get("decidedByLabel") or "", "decided_at": r.get("decidedAt"), "posted_nos": r.get("postedNos") or [],
        })
    for a in p.get("advances") or []:
        status = a.get("status") if a.get("status") in ("pending", "approved", "rejected") else "pending"
        import_repo.insert_advance(conn, {
            "employee": a["employee"].strip(), "amount": a["amount"], "installments": int(a.get("installments") or 1),
            "reason": a.get("reason") or "", "status": status, "created_by": owner["id"],
            "created_by_label": a.get("byLabel") or "", "created_at": a.get("at") or now_iso(),
            "decided_by": owner["id"] if status != "pending" else None, "decided_by_label": a.get("decidedByLabel") or "",
            "decided_at": a.get("decidedAt"), "entry_no": a.get("entryNo"),
        })
    for b in p.get("budgets") or []:
        settings_repo.save_budget(conn, b["month"], {k: v for k, v in b.items() if k not in ("id", "month") and _num(v)})
    if p.get("recon"):
        settings_repo.save(conn, {"legacyRecon": p["recon"]})

    return {"entries": len(entries), "assets": len(p.get("assets") or []), "shifts": len(p.get("shifts") or []),
            "parties": len(parties), "requests": len(p.get("requests") or []), "advances": len(p.get("advances") or [])}


# ---------------------------------------------------------------- verification (inside the transaction)

def figures(conn: sqlite3.Connection) -> dict[str, Any]:
    """Balances recomputed from the database, the way the prototype computed them
    (reversed entries and their mirror entries excluded)."""
    by_acc = {r["k"]: r for r in entries_repo.sums_by(conn, "account", live=True)}
    by_party = {r["k"]: r for r in entries_repo.sums_by(conn, "account_party", live=True, accounts=PARTY_ACCOUNTS)}
    counts = fetch_one(conn, "SELECT COUNT(*) AS n, SUM(status = 'posted') AS posted, SUM(status = 'reversed') AS reversed, "
                             "MAX(no) AS max_no FROM entries")
    return {
        "trialBalance": r2(sum(r["y"] for r in by_acc.values())),
        "yer": {k: r["y"] for k, r in by_acc.items()},
        "sar": {k: r["fc"] for k, r in by_acc.items()},
        "qty": {k: r["q"] for k, r in by_acc.items()},
        "partyYer": {k: r["y"] for k, r in by_party.items()},
        "partySar": {k: r["fc"] for k, r in by_party.items()},
        "entries": counts["n"], "entriesPosted": counts["posted"] or 0, "entriesReversed": counts["reversed"] or 0,
        "maxNo": counts["max_no"] or 0,
        "assets": fetch_one(conn, "SELECT COUNT(*) AS n FROM assets")["n"],
        "shifts": fetch_one(conn, "SELECT COUNT(*) AS n FROM shifts")["n"],
    }


def compare(f: dict[str, Any], expected: dict[str, Any]) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []

    def check(name: str, got: float, want: Any) -> None:
        if want is None:
            return
        if not _num(want) or abs((got or 0) - want) > TOL:
            diffs.append({"item": name, "expected": want, "actual": r2(got or 0)})

    check("trialBalance", f["trialBalance"], expected.get("trialBalance"))
    for key in ("entries", "entriesPosted", "entriesReversed", "maxNo", "assets", "shifts"):
        check(key, f[key], expected.get(key))
    for group, src in (("accountBalancesYER", "yer"), ("accountBalancesSAR", "sar"), ("quantities", "qty"),
                       ("partyBalancesYER", "partyYer"), ("partyBalancesSAR", "partySar")):
        for k, want in (expected.get(group) or {}).items():
            check(f"{group}[{k}]", f[src].get(k, 0), want)
    return diffs


def key_balances(f: dict[str, Any]) -> dict[str, float]:
    return {"1102_SAR": f["sar"].get("1102", 0), "1103": f["yer"].get("1103", 0), "1301_qty": f["qty"].get("1301", 0),
            "1305_qty": f["qty"].get("1305", 0), "2104": f["yer"].get("2104", 0)}


# ---------------------------------------------------------------- entry point

def import_export(conn: sqlite3.Connection, raw: bytes) -> dict[str, Any]:
    digest = hashlib.sha256(raw).hexdigest()
    done = import_repo.get_log(conn)
    if done:
        if done["sha256"] == digest:
            return {**done["summary"], "alreadyImported": True}
        raise Conflict(f"تم الاستيراد مسبقاً في {done['done_at']}؛ لا يُقبل ملف مختلف")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise Unprocessable("الملف ليس JSON صحيحاً")
    if not isinstance(payload, dict):
        raise Unprocessable("الملف يجب أن يكون كائن JSON")

    _validate(payload)
    with transaction(conn):
        counts = import_repo.ledger_counts(conn)
        if counts["entries"] or counts["shifts"] or counts["assets"]:
            raise Conflict("الدفاتر ليست فارغة: الاستيراد يعمل على قاعدة بيانات جديدة فقط", None, {"existing": counts})
        owner = _owner(conn)
        imported = _write(conn, payload, owner)
        f = figures(conn)
        diffs = compare(f, payload.get("expected") or {})
        if diffs:
            raise Unprocessable(f"الأرقام بعد الاستيراد لا تطابق الملف ({len(diffs)} فرق)؛ لم يُحفظ شيء", "expected",
                                {"differences": diffs})
        summary = {"imported": imported, "nextEntryNo": entries_repo.next_no(conn), "trialBalance": f["trialBalance"],
                   "matchesExpected": True, "keyBalances": key_balances(f)}
        import_repo.add_log(conn, digest, now_iso(), summary)
    logger.info("Prototype import done: %s", imported)
    return {**summary, "alreadyImported": False}
