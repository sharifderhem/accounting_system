"""Journal entries and their lines.

Amounts are stored in minor units and returned to services in rials. ``fc`` and
``qty`` are stored as positive numbers; their sign comes from the side of the line
(debit adds, credit subtracts), exactly as in the prototype.
"""

import json
import sqlite3
from typing import Any, Iterable

from database import execute, fetch_all, fetch_one
from utils.money import from_minor, to_minor

_ENTRY_COLS = (
    "e.id, e.no, e.date, e.memo, e.src, e.ref, e.party, e.status, e.reverses_id, e.reversed_by_id, "
    "e.is_cogs, e.created_by, e.created_by_label, e.created_at, e.approved_by, e.approved_by_label, e.meta"
)
_LINE_COLS = "l.id, l.entry_id, l.seq, l.account, l.debit, l.credit, l.party, l.cur, l.fc, l.qty, l.shift, l.cc, l.asset, l.memo"

# Signed helpers used in aggregate queries.
_SIGN = "(CASE WHEN l.debit > 0 THEN 1 ELSE -1 END)"
_SUMS = (
    "COALESCE(SUM(l.debit - l.credit), 0) AS y, "
    f"COALESCE(SUM(CASE WHEN l.cur = 'SAR' THEN {_SIGN} * COALESCE(l.fc, 0) ELSE 0 END), 0) AS fc, "
    f"COALESCE(SUM({_SIGN} * COALESCE(l.qty, 0)), 0) AS q"
)


def _line_out(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"id": row["id"], "a": row["account"], "d": from_minor(row["debit"]), "c": from_minor(row["credit"])}
    for key in ("party", "cur", "shift", "cc", "asset", "memo"):
        if row.get(key) not in (None, ""):
            out[key] = row[key]
    if row.get("cur") == "SAR":
        out["fc"] = from_minor(row.get("fc"))
    if row.get("qty") is not None:
        out["qty"] = row["qty"]
    return out


def _entry_out(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    row["meta"] = json.loads(row.get("meta") or "{}")
    row["is_cogs"] = bool(row.get("is_cogs"))
    return row


# ---- writes ----

def next_no(conn: sqlite3.Connection) -> int:
    """Must be called inside the posting transaction (write lock held)."""
    return fetch_one(conn, "SELECT COALESCE(MAX(no), 0) + 1 AS n FROM entries")["n"]


def insert_entry(conn: sqlite3.Connection, entry: dict[str, Any], no: int, created_at: str) -> int:
    entry_id = execute(
        conn,
        "INSERT INTO entries (no, date, memo, src, ref, party, status, reverses_id, is_cogs, created_by, "
        "created_by_label, created_at, approved_by, approved_by_label, meta) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            no, entry["date"], entry["memo"], entry["src"], entry.get("ref") or "", entry.get("party") or "",
            entry.get("status") or "posted", entry.get("reverses_id"), int(bool(entry.get("is_cogs"))),
            entry.get("created_by"), entry.get("created_by_label") or "", created_at,
            entry.get("approved_by"), entry.get("approved_by_label") or "",
            json.dumps(entry.get("meta") or {}, ensure_ascii=False),
        ),
    )
    for seq, line in enumerate(entry["lines"]):
        execute(
            conn,
            "INSERT INTO entry_lines (entry_id, seq, account, debit, credit, party, cur, fc, qty, shift, cc, asset, memo) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                entry_id, seq, line["a"], to_minor(line.get("d")), to_minor(line.get("c")), line.get("party") or None,
                line.get("cur") or None, to_minor(line.get("fc")) if line.get("cur") == "SAR" else None,
                line.get("qty") if line.get("qty") else None, line.get("shift") or None, line.get("cc") or None,
                line.get("asset") or None, line.get("memo") or None,
            ),
        )
    return entry_id


def mark_reversed(conn: sqlite3.Connection, entry_id: int, reversal_id: int) -> None:
    execute(conn, "UPDATE entries SET status = 'reversed', reversed_by_id = ? WHERE id = ?", (reversal_id, entry_id))


# ---- single entries ----

def get(conn: sqlite3.Connection, entry_id: int) -> dict[str, Any] | None:
    row = fetch_one(conn, f"SELECT {_ENTRY_COLS} FROM entries e WHERE e.id = ?", (entry_id,))
    if not row:
        return None
    entry = _entry_out(row)
    entry["lines"] = lines_of(conn, [entry_id]).get(entry_id, [])
    return entry


def lines_of(conn: sqlite3.Connection, entry_ids: Iterable[int]) -> dict[int, list[dict[str, Any]]]:
    ids = list(entry_ids)
    out: dict[int, list[dict[str, Any]]] = {i: [] for i in ids}
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        marks = ",".join("?" * len(chunk))
        for row in fetch_all(conn, f"SELECT {_LINE_COLS} FROM entry_lines l WHERE l.entry_id IN ({marks}) ORDER BY l.entry_id, l.seq", chunk):
            out[row["entry_id"]].append(_line_out(row))
    return out


def find_ref(conn: sqlite3.Connection, src: str, ref: str) -> int | None:
    """Number of a live (not reversed, not reversal, not COGS) entry with this source and reference."""
    row = fetch_one(
        conn,
        "SELECT no FROM entries WHERE src = ? AND ref = ? AND status = 'posted' AND reverses_id IS NULL AND is_cogs = 0",
        (src, ref),
    )
    return row["no"] if row else None


# ---- aggregates ----

def _filters(f: dict[str, Any]) -> tuple[str, list[Any]]:
    """Build a WHERE clause from a fixed set of filter keys (never from user-chosen column names)."""
    where, params = ["1 = 1"], []
    if f.get("account"):
        where.append("l.account = ?"); params.append(f["account"])
    if f.get("accounts"):
        accs = list(f["accounts"])
        where.append(f"l.account IN ({','.join('?' * len(accs))})"); params += accs
    if f.get("prefix"):
        where.append("l.account LIKE ?"); params.append(f["prefix"] + "%")
    if "party" in f and f["party"] is not None:
        where.append("l.party = ?"); params.append(f["party"])
    if f.get("until"):
        where.append("e.date <= ?"); params.append(f["until"])
    if f.get("since"):
        where.append("e.date >= ?"); params.append(f["since"])
    if f.get("before"):
        where.append("e.date < ?"); params.append(f["before"])
    if f.get("on"):
        where.append("e.date = ?"); params.append(f["on"])
    if f.get("src"):
        srcs = [f["src"]] if isinstance(f["src"], str) else list(f["src"])
        where.append(f"e.src IN ({','.join('?' * len(srcs))})"); params += srcs
    if f.get("not_src"):
        srcs = [f["not_src"]] if isinstance(f["not_src"], str) else list(f["not_src"])
        where.append(f"e.src NOT IN ({','.join('?' * len(srcs))})"); params += srcs
    if f.get("side") == "d":
        where.append("l.debit > 0")
    elif f.get("side") == "c":
        where.append("l.credit > 0")
    if f.get("shift"):
        where.append("l.shift = ?"); params.append(f["shift"])
    if f.get("asset"):
        where.append("l.asset = ?"); params.append(f["asset"])
    if f.get("cur") == "SAR":
        where.append("l.cur = 'SAR'")
    if f.get("live"):
        # Operational view (charts, open items): ignore reversed entries and their reversals.
        where.append("e.status = 'posted' AND e.reverses_id IS NULL")
    if f.get("not_cogs"):
        where.append("e.is_cogs = 0")
    return " AND ".join(where), params


def sums(conn: sqlite3.Connection, **f: Any) -> dict[str, float]:
    """Net debit−credit (YER), signed SAR amount and signed quantity for matching lines."""
    where, params = _filters(f)
    row = fetch_one(conn, f"SELECT {_SUMS} FROM entry_lines l JOIN entries e ON e.id = l.entry_id WHERE {where}", params)
    return {"y": from_minor(row["y"]), "fc": from_minor(row["fc"]), "q": round(row["q"] or 0, 4)}


def sums_by(conn: sqlite3.Connection, group: str, **f: Any) -> list[dict[str, Any]]:
    """The same sums grouped by one of a fixed set of keys."""
    columns = {"account": "l.account", "party": "l.party", "date": "e.date", "cc": "l.cc", "src": "e.src",
               "account_party": "l.account || '|' || COALESCE(l.party, '')", "asset": "l.asset"}
    col = columns[group]
    where, params = _filters(f)
    rows = fetch_all(
        conn,
        f"SELECT {col} AS k, {_SUMS} FROM entry_lines l JOIN entries e ON e.id = l.entry_id WHERE {where} GROUP BY {col}",
        params,
    )
    return [{"k": r["k"], "y": from_minor(r["y"]), "fc": from_minor(r["fc"]), "q": round(r["q"] or 0, 4)} for r in rows]


def parties_on(conn: sqlite3.Connection, account: str) -> list[str]:
    rows = fetch_all(
        conn,
        "SELECT l.party, MIN(l.id) AS first FROM entry_lines l WHERE l.account = ? AND l.party IS NOT NULL "
        "GROUP BY l.party ORDER BY first",
        (account,),
    )
    return [r["party"] for r in rows]


# ---- line listings ----

def lines_with_entries(conn: sqlite3.Connection, **f: Any) -> list[dict[str, Any]]:
    """Matching lines joined with their entry header, in posting order."""
    where, params = _filters(f)
    rows = fetch_all(
        conn,
        f"SELECT {_LINE_COLS}, e.no, e.date, e.memo AS entry_memo, e.src, e.ref, e.status, e.reverses_id, e.is_cogs, e.meta "
        f"FROM entry_lines l JOIN entries e ON e.id = l.entry_id WHERE {where} ORDER BY e.date, e.no, l.seq",
        params,
    )
    out = []
    for r in rows:
        line = _line_out(r)
        line.update({"entry_id": r["entry_id"], "no": r["no"], "date": r["date"], "entry_memo": r["entry_memo"],
                     "src": r["src"], "ref": r["ref"], "status": r["status"], "reverses_id": r["reverses_id"],
                     "is_cogs": bool(r["is_cogs"]), "meta": json.loads(r["meta"] or "{}")})
        out.append(line)
    return out


def list_entries(conn: sqlite3.Connection, where: list[str], params: list[Any], limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    """Journal listing. ``where`` clauses come from the journal service's fixed filter set."""
    clause = " AND ".join(where) if where else "1 = 1"
    total = fetch_one(conn, f"SELECT COUNT(*) AS n FROM entries e WHERE {clause}", params)["n"]
    rows = fetch_all(conn, f"SELECT {_ENTRY_COLS} FROM entries e WHERE {clause} ORDER BY e.no DESC LIMIT ? OFFSET ?",
                     params + [limit, offset])
    entries = [_entry_out(r) for r in rows]
    lines = lines_of(conn, [e["id"] for e in entries])
    for e in entries:
        e["lines"] = lines[e["id"]]
    return entries, total


def debit_total(conn: sqlite3.Connection, where: list[str], params: list[Any]) -> float:
    clause = " AND ".join(where) if where else "1 = 1"
    row = fetch_one(
        conn,
        f"SELECT COALESCE(SUM(l.debit), 0) AS d FROM entry_lines l JOIN entries e ON e.id = l.entry_id "
        f"WHERE {clause} AND e.status = 'posted' AND e.reverses_id IS NULL",
        params,
    )
    return from_minor(row["d"])


def entries_where(conn: sqlite3.Connection, where: list[str], params: list[Any]) -> list[dict[str, Any]]:
    clause = " AND ".join(where) if where else "1 = 1"
    return [_entry_out(r) for r in fetch_all(conn, f"SELECT {_ENTRY_COLS} FROM entries e WHERE {clause} ORDER BY e.date, e.no", params)]


def last_activity_date(conn: sqlite3.Connection, until: str) -> str | None:
    row = fetch_one(conn, "SELECT MAX(date) AS d FROM entries WHERE date <= ? AND src <> 'rev'", (until,))
    return row["d"] if row else None
