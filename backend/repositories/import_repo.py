"""Writes used only by the one-time prototype import. Rows are copied as they are."""

import json
import sqlite3
from typing import Any

from database import execute, fetch_all, fetch_one
from utils.money import to_minor


def ledger_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: fetch_one(conn, f"SELECT COUNT(*) AS n FROM {t}")["n"]
            for t in ("entries", "shifts", "assets", "requests", "advances")}


def get_log(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = fetch_one(conn, "SELECT sha256, done_at, summary FROM import_log ORDER BY id LIMIT 1")
    return {**row, "summary": json.loads(row["summary"])} if row else None


def add_log(conn: sqlite3.Connection, sha256: str, done_at: str, summary: dict[str, Any]) -> None:
    execute(conn, "INSERT INTO import_log (sha256, done_at, summary) VALUES (?,?,?)",
            (sha256, done_at, json.dumps(summary, ensure_ascii=False)))


def upsert_party(conn: sqlite3.Connection, name: str, type_: str) -> None:
    execute(conn, "INSERT INTO parties (name, type) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET type = excluded.type",
            (name, type_))


def entry_ids_by_legacy(conn: sqlite3.Connection) -> dict[str, int]:
    return {r["legacy_id"]: r["id"] for r in fetch_all(conn, "SELECT id, legacy_id FROM entries WHERE legacy_id IS NOT NULL")}


def insert_shift(conn: sqlite3.Connection, s: dict[str, Any]) -> int:
    return execute(
        conn,
        "INSERT INTO shifts (date, shift, by_name, meter_start, meter_end, bags, extra_kg, cartons, scrap_kg, shots_start, "
        "shots_end, down_min, down_reason, notes, status, entry_id, cost, created_by, created_at, decided_by, decided_at, "
        "legacy_id, doc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (s["date"], s["shift"], s["by_name"], s["meter_start"], s["meter_end"], s["bags"], s["extra_kg"], s["cartons"],
         s["scrap_kg"], s["shots_start"], s["shots_end"], s["down_min"], s["down_reason"], s["notes"], s["status"],
         s["entry_id"], json.dumps(s["cost"], ensure_ascii=False) if s["cost"] else None, s["created_by"], s["created_at"],
         s["decided_by"], s["decided_at"], s["legacy_id"], json.dumps(s["doc"], ensure_ascii=False)),
    )


def insert_request(conn: sqlite3.Connection, r: dict[str, Any]) -> None:
    execute(
        conn,
        "INSERT INTO requests (kind, entries, summary, amount, status, created_by, created_by_label, created_at, decided_by, "
        "decided_by_label, decided_at, posted_nos) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (r["kind"], json.dumps(r["entries"], ensure_ascii=False), r["summary"], to_minor(r["amount"]), r["status"],
         r["created_by"], r["created_by_label"], r["created_at"], r["decided_by"], r["decided_by_label"], r["decided_at"],
         json.dumps(r["posted_nos"])),
    )


def insert_advance(conn: sqlite3.Connection, a: dict[str, Any]) -> None:
    execute(
        conn,
        "INSERT INTO advances (employee, amount, installments, reason, status, created_by, created_by_label, created_at, "
        "decided_by, decided_by_label, decided_at, entry_no) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (a["employee"], to_minor(a["amount"]), a["installments"], a["reason"], a["status"], a["created_by"],
         a["created_by_label"], a["created_at"], a["decided_by"], a["decided_by_label"], a["decided_at"], a["entry_no"]),
    )
