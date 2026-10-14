"""Settings, parties and cost centers (spec §2, §4, §9, §15)."""

import re
import sqlite3
from typing import Any

from database import transaction
from repositories import settings_repo
from services.chart import (
    DEFAULT_COST_CENTERS, DEFAULT_PARTIES, DEFAULT_SETTINGS, NUMERIC_SETTINGS, PARTY_TYPES, POSITIVE_SETTINGS,
)
from utils.dates import is_iso
from utils.errors import DomainError, need
from utils.money import is_num


def get(conn: sqlite3.Connection) -> dict[str, Any]:
    stored = settings_repo.load_stored(conn)
    return {**DEFAULT_SETTINGS, **stored}


def seed(conn: sqlite3.Connection, owner_name: str) -> None:
    """First start: the agreed parties and cost centers (§4, §9). Safe to rerun."""
    with transaction(conn):
        if not settings_repo.list_cost_centers(conn):
            for cc_id, name in DEFAULT_COST_CENTERS:
                settings_repo.add_cost_center(conn, cc_id, name)
        if not settings_repo.list_parties(conn):
            for name, type_ in DEFAULT_PARTIES:
                settings_repo.add_party(conn, name, type_)
            if owner_name and not settings_repo.get_party(conn, owner_name):
                settings_repo.add_party(conn, owner_name, "owner")


def update(conn: sqlite3.Connection, values: dict[str, Any]) -> dict[str, Any]:
    """Owner edits from the settings screen. Unknown keys are ignored."""
    clean: dict[str, Any] = {}
    for key in NUMERIC_SETTINGS:
        if key in values:
            v = values[key]
            need(is_num(v) and v >= 0, f"قيمة غير صحيحة في الإعداد {key}", key)
            if key in POSITIVE_SETTINGS:
                need(v > 0, f"الإعداد {key} يجب أن يكون أكبر من صفر", key)
            clean[key] = v
    if "chillerLoad" in clean:
        need(clean["chillerLoad"] <= 1, "نسبة تشغيل المبرد بين 0 و 1", "chillerLoad")
    for key in ("costingStart",):
        if key in values:
            need(is_iso(values[key]), "تاريخ غير صحيح", key)
            clean[key] = values[key]
    if "lockDate" in values:
        need(values["lockDate"] in ("", None) or is_iso(values["lockDate"]), "تاريخ الإقفال غير صحيح", "lockDate")
        clean["lockDate"] = values["lockDate"] or ""
    for key in ("vatEnabled", "dualControl"):
        if key in values:
            clean[key] = bool(values[key])
    if "vatNo" in values:
        clean["vatNo"] = str(values["vatNo"] or "")[:40]
    if "creditLimits" in values:
        limits = values["creditLimits"] or {}
        need(isinstance(limits, dict), "سقوف الائتمان غير صحيحة")
        clean["creditLimits"] = {str(k): float(v) for k, v in limits.items() if is_num(v) and v > 0}
    if "provPct" in values:
        pct = values["provPct"]
        need(isinstance(pct, list) and len(pct) == 5 and all(is_num(p) and 0 <= p <= 100 for p in pct),
             "نسب المخصص غير صحيحة")
        clean["provPct"] = pct
    with transaction(conn):
        settings_repo.save(conn, clean)
    return get(conn)


def set_credit_limits(conn: sqlite3.Connection, limits: dict[str, Any]) -> dict[str, Any]:
    return update(conn, {"creditLimits": limits})


# ---- parties ----

def parties(conn: sqlite3.Connection, type_: str | None = None) -> list[dict[str, Any]]:
    return settings_repo.list_parties(conn, type_)


def party_names(conn: sqlite3.Connection, type_: str | None = None) -> list[str]:
    return [p["name"] for p in settings_repo.list_parties(conn, type_)]


def owner_name(conn: sqlite3.Connection) -> str:
    return settings_repo.owner_name(conn)


def add_party(conn: sqlite3.Connection, name: str, type_: str) -> dict[str, Any]:
    name = (name or "").strip()
    need(name, "اكتب الاسم", "name")
    need(type_ in PARTY_TYPES, "نوع الطرف غير صحيح", "type")
    with transaction(conn):
        if settings_repo.get_party(conn, name):
            raise DomainError("الاسم موجود", "name")
        settings_repo.add_party(conn, name, type_)
    return settings_repo.get_party(conn, name)


# ---- cost centers ----

def cost_centers(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return settings_repo.list_cost_centers(conn)


def add_cost_center(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    name = (name or "").strip()
    need(name, "اكتب اسم المركز", "name")
    existing = cost_centers(conn)
    need(not any(c["name"] == name for c in existing), "المركز موجود", "name")
    base = re.sub(r"[^a-z0-9]", "", name.lower())[:10] or "cc"
    cc_id, n = base, 2
    ids = {c["id"] for c in existing}
    while cc_id in ids:
        cc_id, n = f"{base}{n}", n + 1
    with transaction(conn):
        settings_repo.add_cost_center(conn, cc_id, name)
    return {"id": cc_id, "name": name}


def cc_ids(conn: sqlite3.Connection) -> set[str]:
    return {c["id"] for c in cost_centers(conn)}
