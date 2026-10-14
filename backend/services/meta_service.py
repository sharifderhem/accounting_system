"""What the app needs to draw its forms for the signed-in user, filtered by role."""

import sqlite3
from typing import Any

from repositories import requests_repo, shifts_repo
from services import access, ledger_service, requests_service, settings_service, transactions_service
from services.chart import (
    ACCOUNTS, DOWN_REASONS, EXP_CATS, OUT_PURPOSES, PARTY_TYPES, QTY_PURPOSES, PARTY_PURPOSES, ROLES, SOURCES, VIA,
)

FORM_SETTINGS = ("fx", "priceSar", "vatEnabled", "vatRate", "costingStart", "cartonCost", "bagKg")


def tabs_for(user: dict[str, Any]) -> list[str]:
    role = user["role"]
    if role == "owner":
        return ["home", "shifts", "move", "requests", "analytics", "recon", "assets", "reports", "journal", "settings"]
    if role == "entry":
        return ["move", "requests"]
    if role == "reviewer":
        return ["home", "analytics", "reports", "journal", "recon"] + (["requests"] if access.is_approver(user) else [])
    if role == "supervisor":
        return ["sup"]
    return []


def badges(conn: sqlite3.Connection, user: dict[str, Any]) -> dict[str, int]:
    out = {}
    if access.is_owner(user):
        out["shifts"] = shifts_repo.pending_count(conn)
    if access.is_approver(user):
        reqs = [r for r in requests_repo.list_requests(conn) if r["status"] == "pending" and r["created_by"] != user["id"]]
        advs = [a for a in requests_repo.list_advances(conn) if a["status"] == "pending" and requests_service.can_approve_advance(user, a)]
        out["requests"] = len(reqs) + len(advs)
    return out


def context(conn: sqlite3.Connection, user: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"user": user, "tabs": tabs_for(user), "roles": ROLES, "badges": badges(conn, user),
                           "downReasons": list(DOWN_REASONS), "employees": requests_service.employee_names(conn)}
    s = settings_service.get(conn)
    if user["role"] == "supervisor":
        out["settings"] = {"bagKg": s["bagKg"]}
        out["lastMeter"] = shifts_repo.last_meter_end(conn)
        return out
    out["settings"] = {k: s[k] for k in FORM_SETTINGS}
    out["accounts"] = {k: {"name": v[0], "type": v[1], "cur": v[2], "unit": v[3]} for k, v in ACCOUNTS.items()}
    out["sources"] = SOURCES
    out["partyTypes"] = PARTY_TYPES
    out["parties"] = settings_service.parties(conn)
    out["ownerName"] = settings_service.owner_name(conn)
    out["costCenters"] = settings_service.cost_centers(conn)
    out["expCats"] = {k: v[0] for k, v in EXP_CATS.items()}
    out["outPurposes"] = {k: v[0] for k, v in OUT_PURPOSES.items()}
    out["qtyPurposes"] = list(QTY_PURPOSES)
    out["partyPurposes"] = list(PARTY_PURPOSES)
    out["via"] = {k: v[0] for k, v in VIA.items()}
    out["forms"] = list(access.forms_for(user))
    out["needsApproval"] = {k: transactions_service.needs_approval(conn, k, user) for k in transactions_service.DUAL_CONTROL_KINDS}
    if access.is_owner(user):
        out["lastMeter"] = shifts_repo.last_meter_end(conn)
    if access.sees_finance(user):
        # Header chips: the SAR and YER accounts, always shown separately (§1.4).
        out["headline"] = {"sar": ledger_service.bal(conn, "1102")["fc"], "yer": ledger_service.bal(conn, "1103")["y"]}
    return out
