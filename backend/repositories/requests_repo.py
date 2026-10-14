"""Payment requests (dual control) and employee advance requests."""

import json
import sqlite3
from typing import Any

from database import execute, fetch_all, fetch_one
from utils.money import from_minor, to_minor

_REQ_COLS = ("id, kind, entries, summary, amount, status, created_by, created_by_label, created_at, decided_by, "
             "decided_by_label, decided_at, posted_nos")
_ADV_COLS = ("id, employee, amount, installments, reason, status, created_by, created_by_label, created_at, decided_by, "
             "decided_by_label, decided_at, entry_no")


def _req(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    row = dict(row)
    row["entries"] = json.loads(row["entries"])
    row["posted_nos"] = json.loads(row["posted_nos"] or "[]")
    row["amount"] = from_minor(row["amount"])
    return row


def _adv(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    row = dict(row)
    row["amount"] = from_minor(row["amount"])
    return row


# ---- payment requests ----

def insert_request(conn: sqlite3.Connection, kind: str, entries: list[dict], summary: str, amount: float,
                   created_by: int, created_by_label: str, created_at: str) -> int:
    return execute(
        conn,
        "INSERT INTO requests (kind, entries, summary, amount, created_by, created_by_label, created_at) VALUES (?,?,?,?,?,?,?)",
        (kind, json.dumps(entries, ensure_ascii=False), summary, to_minor(amount), created_by, created_by_label, created_at),
    )


def get_request(conn: sqlite3.Connection, req_id: int) -> dict[str, Any] | None:
    return _req(fetch_one(conn, f"SELECT {_REQ_COLS} FROM requests WHERE id = ?", (req_id,)))


def list_requests(conn: sqlite3.Connection, created_by: int | None = None, limit: int = 200) -> list[dict[str, Any]]:
    if created_by is not None:
        rows = fetch_all(conn, f"SELECT {_REQ_COLS} FROM requests WHERE created_by = ? "
                               "ORDER BY status = 'pending' DESC, created_at DESC LIMIT ?", (created_by, limit))
    else:
        rows = fetch_all(conn, f"SELECT {_REQ_COLS} FROM requests ORDER BY status = 'pending' DESC, created_at DESC LIMIT ?", (limit,))
    return [_req(r) for r in rows]


def decide_request(conn: sqlite3.Connection, req_id: int, status: str, decided_by: int, decided_by_label: str,
                   decided_at: str, posted_nos: list[int] | None = None) -> None:
    execute(
        conn,
        "UPDATE requests SET status = ?, decided_by = ?, decided_by_label = ?, decided_at = ?, posted_nos = ? WHERE id = ?",
        (status, decided_by, decided_by_label, decided_at, json.dumps(posted_nos or []), req_id),
    )


def pending_requests(conn: sqlite3.Connection) -> int:
    return fetch_one(conn, "SELECT COUNT(*) AS n FROM requests WHERE status = 'pending'")["n"]


# ---- advance requests ----

def insert_advance(conn: sqlite3.Connection, employee: str, amount: float, installments: int, reason: str,
                   created_by: int, created_by_label: str, created_at: str) -> int:
    return execute(
        conn,
        "INSERT INTO advances (employee, amount, installments, reason, created_by, created_by_label, created_at) VALUES (?,?,?,?,?,?,?)",
        (employee, to_minor(amount), installments, reason, created_by, created_by_label, created_at),
    )


def get_advance(conn: sqlite3.Connection, adv_id: int) -> dict[str, Any] | None:
    return _adv(fetch_one(conn, f"SELECT {_ADV_COLS} FROM advances WHERE id = ?", (adv_id,)))


def list_advances(conn: sqlite3.Connection, created_by: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
    if created_by is not None:
        rows = fetch_all(conn, f"SELECT {_ADV_COLS} FROM advances WHERE created_by = ? "
                               "ORDER BY status = 'pending' DESC, created_at DESC LIMIT ?", (created_by, limit))
    else:
        rows = fetch_all(conn, f"SELECT {_ADV_COLS} FROM advances ORDER BY status = 'pending' DESC, created_at DESC LIMIT ?", (limit,))
    return [_adv(r) for r in rows]


def decide_advance(conn: sqlite3.Connection, adv_id: int, status: str, decided_by: int, decided_by_label: str,
                   decided_at: str, entry_no: int | None = None) -> None:
    execute(
        conn,
        "UPDATE advances SET status = ?, decided_by = ?, decided_by_label = ?, decided_at = ?, entry_no = ? WHERE id = ?",
        (status, decided_by, decided_by_label, decided_at, entry_no, adv_id),
    )


def pending_advances(conn: sqlite3.Connection) -> int:
    return fetch_one(conn, "SELECT COUNT(*) AS n FROM advances WHERE status = 'pending'")["n"]


def employee_names(conn: sqlite3.Connection) -> list[str]:
    return [r["employee"] for r in fetch_all(conn, "SELECT DISTINCT employee FROM advances ORDER BY employee")]
