"""Factory settings, parties and cost centers."""

import json
import sqlite3
from typing import Any

from database import execute, fetch_all, fetch_one


def load_stored(conn: sqlite3.Connection) -> dict[str, Any]:
    """Only the settings that were saved. The service fills in defaults."""
    return {r["key"]: json.loads(r["value"]) for r in fetch_all(conn, "SELECT key, value FROM settings")}


def save(conn: sqlite3.Connection, values: dict[str, Any]) -> None:
    for key, value in values.items():
        execute(
            conn,
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )


# ---- parties ----

def list_parties(conn: sqlite3.Connection, type_: str | None = None) -> list[dict[str, Any]]:
    if type_:
        return fetch_all(conn, "SELECT id, name, type FROM parties WHERE type = ? ORDER BY id", (type_,))
    return fetch_all(conn, "SELECT id, name, type FROM parties ORDER BY id")


def get_party(conn: sqlite3.Connection, name: str) -> dict[str, Any] | None:
    return fetch_one(conn, "SELECT id, name, type FROM parties WHERE name = ?", (name,))


def add_party(conn: sqlite3.Connection, name: str, type_: str) -> int:
    return execute(conn, "INSERT INTO parties (name, type) VALUES (?, ?)", (name, type_))


def owner_name(conn: sqlite3.Connection) -> str:
    row = fetch_one(conn, "SELECT name FROM parties WHERE type = 'owner' ORDER BY id LIMIT 1")
    return row["name"] if row else "المالك"


# ---- cost centers ----

def list_cost_centers(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return fetch_all(conn, "SELECT id, name FROM cost_centers ORDER BY rowid")


def add_cost_center(conn: sqlite3.Connection, cc_id: str, name: str) -> None:
    execute(conn, "INSERT INTO cost_centers (id, name) VALUES (?, ?)", (cc_id, name))


# ---- monthly budgets ----

def get_budget(conn: sqlite3.Connection, month: str) -> dict[str, Any]:
    row = fetch_one(conn, "SELECT data FROM budgets WHERE month = ?", (month,))
    return json.loads(row["data"]) if row else {}


def save_budget(conn: sqlite3.Connection, month: str, data: dict[str, Any]) -> None:
    execute(conn, "INSERT INTO budgets (month, data) VALUES (?, ?) ON CONFLICT(month) DO UPDATE SET data = excluded.data",
            (month, json.dumps(data)))
