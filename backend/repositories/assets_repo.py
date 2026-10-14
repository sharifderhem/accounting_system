"""Fixed assets register."""

import sqlite3
from typing import Any

from database import execute, fetch_all, fetch_one
from utils.money import from_minor, to_minor

_COLS = "id, name, date, cost, amount, cur, life, salvage, cc, note, posted_to, created_at"


def _out(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    row = dict(row)
    row["cost"] = from_minor(row["cost"])
    row["salvage"] = from_minor(row["salvage"])
    return row


def list_all(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [_out(r) for r in fetch_all(conn, f"SELECT {_COLS} FROM assets ORDER BY date, created_at")]


def get(conn: sqlite3.Connection, asset_id: str) -> dict[str, Any] | None:
    return _out(fetch_one(conn, f"SELECT {_COLS} FROM assets WHERE id = ?", (asset_id,)))


def insert(conn: sqlite3.Connection, a: dict[str, Any]) -> None:
    execute(
        conn,
        f"INSERT INTO assets ({_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (a["id"], a["name"], a["date"], to_minor(a.get("cost")), a.get("amount") or 0, a.get("cur") or "YER", a["life"],
         to_minor(a.get("salvage")), a.get("cc") or "prod", a.get("note") or "", a.get("posted_to"), a["created_at"]),
    )


_UPDATABLE = {"cost", "amount", "cur", "life", "note", "posted_to", "salvage"}


def update(conn: sqlite3.Connection, asset_id: str, **fields: Any) -> None:
    cols = [k for k in fields if k in _UPDATABLE]
    if not cols:
        return
    values = [to_minor(fields[c]) if c in ("cost", "salvage") else fields[c] for c in cols]
    execute(conn, f"UPDATE assets SET {', '.join(f'{c} = ?' for c in cols)} WHERE id = ?", values + [asset_id])
