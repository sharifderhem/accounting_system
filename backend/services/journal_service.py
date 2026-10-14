"""Journal listing with filters (spec §16)."""

import sqlite3
from typing import Any

from repositories import entries_repo
from services.chart import ACCOUNTS, SOURCES

MAX_LIMIT = 5000


def search(conn: sqlite3.Connection, f: dict[str, Any], limit: int = 60, offset: int = 0) -> dict[str, Any]:
    where: list[str] = []
    params: list[Any] = []
    if f.get("frm"):
        where.append("e.date >= ?"); params.append(f["frm"])
    if f.get("to"):
        where.append("e.date <= ?"); params.append(f["to"])
    if f.get("src") in SOURCES:
        where.append("e.src = ?"); params.append(f["src"])
    if f.get("party"):
        where.append("(e.party = ? OR EXISTS (SELECT 1 FROM entry_lines x WHERE x.entry_id = e.id AND x.party = ?))")
        params += [f["party"], f["party"]]
    if f.get("account") in ACCOUNTS:
        where.append("EXISTS (SELECT 1 FROM entry_lines x WHERE x.entry_id = e.id AND x.account = ?)")
        params.append(f["account"])
    if f.get("cur") == "SAR":
        where.append("EXISTS (SELECT 1 FROM entry_lines x WHERE x.entry_id = e.id AND x.cur = 'SAR')")
    elif f.get("cur") == "YER":
        where.append("NOT EXISTS (SELECT 1 FROM entry_lines x WHERE x.entry_id = e.id AND x.cur = 'SAR')")
    q = (f.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        clause = ("(e.memo LIKE ? OR e.ref LIKE ? OR EXISTS (SELECT 1 FROM entry_lines x WHERE x.entry_id = e.id AND x.memo LIKE ?)")
        params += [like, like, like]
        if q.isdigit():
            clause += " OR e.no = ?"
            params.append(int(q))
        where.append(clause + ")")
    limit = max(1, min(int(limit or 60), MAX_LIMIT))
    entries, total = entries_repo.list_entries(conn, where, params, limit, max(0, int(offset or 0)))
    return {"entries": entries, "total": total, "debitTotal": entries_repo.debit_total(conn, where, params)}
