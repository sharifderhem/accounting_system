"""Connection management for SQLite.

The ledger uses the standard-library ``sqlite3`` driver. API routes that touch the
database are plain ``def`` functions, which FastAPI runs in its thread pool, so the
blocking driver never stalls the event loop.

Writes that form one business action (post an entry, approve a request, approve a
shift) run inside ``transaction()``, which takes SQLite's write lock up front
(``BEGIN IMMEDIATE``). Only one writer runs at a time, so entry numbers cannot
collide and a half-finished action is always rolled back.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from config import settings


def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict[str, Any]:
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


class Database:
    path: str = settings.database_path

    @classmethod
    def connect(cls, path: str | None = None) -> sqlite3.Connection:
        target = path or cls.path
        if target != ":memory:":
            Path(target).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(target, isolation_level=None, check_same_thread=False, timeout=15)
        conn.row_factory = _dict_factory
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 15000")
        if target != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a block as one atomic write. Nested use joins the outer transaction."""
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def fetch_one(conn: sqlite3.Connection, query: str, params: tuple | list = ()) -> dict[str, Any] | None:
    return conn.execute(query, params).fetchone()


def fetch_all(conn: sqlite3.Connection, query: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    return conn.execute(query, params).fetchall()


def execute(conn: sqlite3.Connection, query: str, params: tuple | list = ()) -> int:
    """Execute a write and return the last inserted row id."""
    return conn.execute(query, params).lastrowid
