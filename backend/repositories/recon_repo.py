"""Statement-matching marks and history (spec §10.2)."""

import sqlite3
from typing import Any

from database import execute, fetch_all
from utils.money import from_minor, to_minor


def marked_lines(conn: sqlite3.Connection, key: str) -> set[int]:
    return {r["line_id"] for r in fetch_all(conn, "SELECT line_id FROM recon_marks WHERE account_key = ?", (key,))}


def replace_marks(conn: sqlite3.Connection, key: str, line_ids: list[int]) -> None:
    execute(conn, "DELETE FROM recon_marks WHERE account_key = ?", (key,))
    for line_id in line_ids:
        execute(conn, "INSERT INTO recon_marks (account_key, line_id) VALUES (?, ?)", (key, line_id))


def add_history(conn: sqlite3.Connection, key: str, date: str, statement: float, book: float, cleared: float,
                diff: float, by_label: str, created_at: str) -> None:
    execute(
        conn,
        "INSERT INTO recon_history (account_key, date, statement, book, cleared, diff, by_label, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (key, date, to_minor(statement), to_minor(book), to_minor(cleared), to_minor(diff), by_label, created_at),
    )


def history(conn: sqlite3.Connection, key: str) -> list[dict[str, Any]]:
    rows = fetch_all(conn, "SELECT date, statement, book, cleared, diff, by_label, created_at FROM recon_history "
                           "WHERE account_key = ? ORDER BY id DESC", (key,))
    return [{**r, **{k: from_minor(r[k]) for k in ("statement", "book", "cleared", "diff")}} for r in rows]
