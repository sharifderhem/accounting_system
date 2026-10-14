"""Users and login sessions."""

import sqlite3
from typing import Any

from database import execute, fetch_all, fetch_one

_USER_COLS = "id, username, label, role, approver, active, failed_logins, locked_until, created_at"


def get_by_id(conn: sqlite3.Connection, user_id: int) -> dict[str, Any] | None:
    return fetch_one(conn, f"SELECT {_USER_COLS} FROM users WHERE id = ?", (user_id,))


def get_auth_by_username(conn: sqlite3.Connection, username: str) -> dict[str, Any] | None:
    return fetch_one(conn, f"SELECT {_USER_COLS}, password_hash FROM users WHERE username = ?", (username,))


def list_all(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return fetch_all(conn, f"SELECT {_USER_COLS} FROM users ORDER BY role = 'owner' DESC, id")


def owner_exists(conn: sqlite3.Connection) -> bool:
    return fetch_one(conn, "SELECT 1 AS x FROM users WHERE role = 'owner' AND active = 1") is not None


def other_approvers(conn: sqlite3.Connection, user_id: int) -> int:
    """Active approvers other than this user. The owner always counts as an approver."""
    row = fetch_one(
        conn,
        "SELECT COUNT(*) AS n FROM users WHERE active = 1 AND id <> ? "
        "AND (role = 'owner' OR (approver = 1 AND role IN ('entry','reviewer')))",
        (user_id,),
    )
    return row["n"]


def create(conn: sqlite3.Connection, username: str, label: str, password_hash: str, role: str,
           approver: bool, created_at: str) -> int:
    return execute(
        conn,
        "INSERT INTO users (username, label, password_hash, role, approver, created_at) VALUES (?,?,?,?,?,?)",
        (username, label, password_hash, role, int(approver), created_at),
    )


_UPDATABLE = {"label", "role", "approver", "active", "password_hash", "failed_logins", "locked_until"}


def update(conn: sqlite3.Connection, user_id: int, **fields: Any) -> None:
    cols = [k for k in fields if k in _UPDATABLE]
    if not cols:
        return
    sets = ", ".join(f"{c} = ?" for c in cols)
    execute(conn, f"UPDATE users SET {sets} WHERE id = ?", [fields[c] for c in cols] + [user_id])


# ---- sessions ----

def create_session(conn: sqlite3.Connection, token_hash: str, user_id: int, created_at: str, expires_at: str) -> None:
    execute(
        conn,
        "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (token_hash, user_id, created_at, expires_at),
    )


def get_session(conn: sqlite3.Connection, token_hash: str) -> dict[str, Any] | None:
    return fetch_one(conn, "SELECT token_hash, user_id, expires_at FROM sessions WHERE token_hash = ?", (token_hash,))


def extend_session(conn: sqlite3.Connection, token_hash: str, expires_at: str) -> None:
    execute(conn, "UPDATE sessions SET expires_at = ? WHERE token_hash = ?", (expires_at, token_hash))


def delete_session(conn: sqlite3.Connection, token_hash: str) -> None:
    execute(conn, "DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


def delete_user_sessions(conn: sqlite3.Connection, user_id: int) -> None:
    execute(conn, "DELETE FROM sessions WHERE user_id = ?", (user_id,))


def delete_expired_sessions(conn: sqlite3.Connection, now: str) -> None:
    execute(conn, "DELETE FROM sessions WHERE expires_at < ?", (now,))
