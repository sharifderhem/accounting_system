"""Production shifts submitted by supervisors."""

import json
import sqlite3
from typing import Any

from database import execute, fetch_all, fetch_one

_COLS = (
    "id, date, shift, by_name, meter_start, meter_end, bags, extra_kg, cartons, scrap_kg, shots_start, shots_end, "
    "down_min, down_reason, notes, status, entry_id, cost, created_by, created_at, decided_by, decided_at"
)


def _out(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    row = dict(row)
    row["cost"] = json.loads(row["cost"]) if row.get("cost") else None
    return row


def get(conn: sqlite3.Connection, shift_id: int) -> dict[str, Any] | None:
    return _out(fetch_one(conn, f"SELECT {_COLS} FROM shifts WHERE id = ?", (shift_id,)))


def list_all(conn: sqlite3.Connection, created_by: int | None = None, status: str | None = None,
             since: str | None = None, until: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    where, params = ["1 = 1"], []
    if created_by is not None:
        where.append("created_by = ?"); params.append(created_by)
    if status:
        where.append("status = ?"); params.append(status)
    if since:
        where.append("date >= ?"); params.append(since)
    if until:
        where.append("date <= ?"); params.append(until)
    sql = f"SELECT {_COLS} FROM shifts WHERE {' AND '.join(where)} ORDER BY date DESC, shift DESC, id DESC"
    if limit:
        sql += " LIMIT ?"; params.append(limit)
    return [_out(r) for r in fetch_all(conn, sql, params)]


def slot_taken(conn: sqlite3.Connection, date: str, shift: str) -> bool:
    return fetch_one(conn, "SELECT 1 AS x FROM shifts WHERE date = ? AND shift = ? AND status <> 'rejected'", (date, shift)) is not None


def last_meter_end(conn: sqlite3.Connection) -> float | None:
    row = fetch_one(conn, "SELECT meter_end FROM shifts WHERE status <> 'rejected' ORDER BY date DESC, shift DESC, id DESC LIMIT 1")
    return row["meter_end"] if row else None


def last_approved(conn: sqlite3.Connection, until: str | None = None) -> dict[str, Any] | None:
    sql = f"SELECT {_COLS} FROM shifts WHERE status = 'approved' AND cost IS NOT NULL"
    params: list[Any] = []
    if until:
        sql += " AND date <= ?"; params.append(until)
    sql += " ORDER BY date DESC, shift DESC, id DESC LIMIT 1"
    return _out(fetch_one(conn, sql, params))


def approved_for(conn: sqlite3.Connection, date: str, shift: str) -> dict[str, Any] | None:
    return _out(fetch_one(conn, f"SELECT {_COLS} FROM shifts WHERE date = ? AND shift = ? AND status = 'approved'", (date, shift)))


def insert(conn: sqlite3.Connection, s: dict[str, Any]) -> int:
    return execute(
        conn,
        "INSERT INTO shifts (date, shift, by_name, meter_start, meter_end, bags, extra_kg, cartons, scrap_kg, shots_start, "
        "shots_end, down_min, down_reason, notes, status, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?)",
        (s["date"], s["shift"], s.get("by_name") or "", s["meter_start"], s["meter_end"], s["bags"], s.get("extra_kg") or 0,
         s["cartons"], s.get("scrap_kg") or 0, s.get("shots_start"), s.get("shots_end"), s.get("down_min") or 0,
         s.get("down_reason") or "", s.get("notes") or "", s["created_by"], s["created_at"]),
    )


def set_status(conn: sqlite3.Connection, shift_id: int, status: str, entry_id: int | None, cost: dict | None,
               decided_by: int | None, decided_at: str | None) -> None:
    execute(
        conn,
        "UPDATE shifts SET status = ?, entry_id = ?, cost = ?, decided_by = ?, decided_at = ? WHERE id = ?",
        (status, entry_id, json.dumps(cost, ensure_ascii=False) if cost else None, decided_by, decided_at, shift_id),
    )


def reset_by_entry(conn: sqlite3.Connection, entry_id: int) -> None:
    execute(conn, "UPDATE shifts SET status = 'pending', entry_id = NULL, cost = NULL, decided_by = NULL, decided_at = NULL "
                  "WHERE entry_id = ?", (entry_id,))


def pending_count(conn: sqlite3.Connection) -> int:
    return fetch_one(conn, "SELECT COUNT(*) AS n FROM shifts WHERE status = 'pending'")["n"]


def update_cost(conn: sqlite3.Connection, shift_id: int, cost: dict[str, Any]) -> None:
    execute(conn, "UPDATE shifts SET cost = ? WHERE id = ?", (json.dumps(cost, ensure_ascii=False), shift_id))
