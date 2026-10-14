"""Dual control (spec §6): payment requests and employee advance requests.

The creator of a request can never approve it. Approval posts the stored entries in
the same transaction that marks the request approved, so a request is never left
approved without its entries, and two approvers clicking at once cannot post twice.
"""

import sqlite3
from typing import Any

from database import transaction
from repositories import requests_repo
from services import access, ledger_service, settings_service, shifts_service
from utils.dates import now_iso, today
from utils.errors import Conflict, Forbidden, NotFound, need
from utils.money import is_num, r2

User = dict[str, Any]
ADVANCE_SOURCES = ("1104", "1101", "1103")


# ---------------------------------------------------------------- payment requests

def create(conn: sqlite3.Connection, kind: str, entries: list[dict[str, Any]], user: User) -> dict[str, Any]:
    amount = r2(sum(sum(line.get("d") or 0 for line in e["lines"]) for e in entries))
    with transaction(conn):
        req_id = requests_repo.insert_request(conn, kind, entries, entries[0]["memo"], amount, user["id"], user["label"], now_iso())
    return public_request(requests_repo.get_request(conn, req_id))


def list_for(conn: sqlite3.Connection, user: User) -> list[dict[str, Any]]:
    """Approvers see every request; everyone else sees only their own (§14)."""
    rows = requests_repo.list_requests(conn) if access.is_approver(user) else requests_repo.list_requests(conn, user["id"])
    return [public_request(r, viewer=user) for r in rows]


def approve(conn: sqlite3.Connection, req_id: int, user: User) -> dict[str, Any]:
    if not access.is_approver(user):
        raise Forbidden("ليست لديك صلاحية اعتماد الطلبات")
    with transaction(conn):
        r = requests_repo.get_request(conn, req_id)
        if not r:
            raise NotFound("الطلب غير موجود")
        if r["status"] != "pending":
            raise Conflict("الطلب لم يعد بانتظار الموافقة")
        if r["created_by"] == user["id"]:
            raise Forbidden("لا يمكنك اعتماد طلب أنشأته بنفسك")
        maker = {"id": r["created_by"], "label": r["created_by_label"]}
        entries = []
        for e in r["entries"]:
            meta = {**(e.get("meta") or {}), "requestId": r["id"], "maker": r["created_by_label"], "checker": user["label"]}
            entries.append({**e, "meta": meta})
        posted = ledger_service.post_many(conn, entries, maker, approver=user)
        if r["kind"] == "exp":
            posted += shifts_service.absorb_late_labor(conn, entries, user)
        nos = [p["no"] for p in posted]
        requests_repo.decide_request(conn, r["id"], "approved", user["id"], user["label"], now_iso(), nos)
    return {"posted": posted}


def reject(conn: sqlite3.Connection, req_id: int, user: User) -> None:
    if not access.is_approver(user):
        raise Forbidden("ليست لديك صلاحية رفض الطلبات")
    with transaction(conn):
        r = _pending(conn, req_id)
        if r["created_by"] == user["id"]:
            raise Forbidden("لسحب طلبك استخدم «سحب الطلب»")
        requests_repo.decide_request(conn, r["id"], "rejected", user["id"], user["label"], now_iso())


def withdraw(conn: sqlite3.Connection, req_id: int, user: User) -> None:
    with transaction(conn):
        r = _pending(conn, req_id)
        if r["created_by"] != user["id"]:
            raise Forbidden("يسحب الطلب من أنشأه فقط")
        requests_repo.decide_request(conn, r["id"], "withdrawn", user["id"], user["label"], now_iso())


def _pending(conn: sqlite3.Connection, req_id: int) -> dict[str, Any]:
    r = requests_repo.get_request(conn, req_id)
    if not r:
        raise NotFound("الطلب غير موجود")
    if r["status"] != "pending":
        raise Conflict("الطلب لم يعد بانتظار الموافقة")
    return r


def public_request(r: dict[str, Any], viewer: User | None = None) -> dict[str, Any]:
    out = {
        "id": r["id"], "kind": r["kind"], "summary": r["summary"], "amount": r["amount"], "status": r["status"],
        "createdBy": r["created_by"], "createdByLabel": r["created_by_label"], "createdAt": r["created_at"],
        "decidedByLabel": r["decided_by_label"], "decidedAt": r["decided_at"], "postedNos": r["posted_nos"],
        "entries": r["entries"],
    }
    if viewer is not None:
        mine = r["created_by"] == viewer["id"]
        out["mine"] = mine
        out["canDecide"] = r["status"] == "pending" and not mine and access.is_approver(viewer)
    return out


# ---------------------------------------------------------------- advance requests (§6.1)

def create_advance(conn: sqlite3.Connection, form: dict[str, Any], user: User) -> dict[str, Any]:
    if not access.can_request_advance(user):
        raise Forbidden("ليست لديك صلاحية طلب السلف")
    employee = str(form.get("employee") or "").strip()
    amount, inst = form.get("amount"), form.get("installments") or 1
    need(employee, "اكتب اسم العامل", "employee")
    need(is_num(amount) and amount > 0, "اكتب المبلغ", "amount")
    need(is_num(inst) and inst >= 1, "عدد دفعات الخصم 1 على الأقل", "installments")
    label = user["label"]
    if user["role"] == "supervisor" and str(form.get("byName") or "").strip():
        label = str(form["byName"]).strip()
    with transaction(conn):
        adv_id = requests_repo.insert_advance(conn, employee, float(amount), int(round(inst)), str(form.get("reason") or "").strip(),
                                              user["id"], label, now_iso())
    return public_advance(conn, requests_repo.get_advance(conn, adv_id), user)


def can_approve_advance(user: User, adv: dict[str, Any]) -> bool:
    return access.is_owner(user) or (access.is_approver(user) and adv["created_by"] != user["id"])


def list_advances(conn: sqlite3.Connection, user: User) -> list[dict[str, Any]]:
    if access.is_approver(user):
        rows = requests_repo.list_advances(conn)
    else:
        rows = requests_repo.list_advances(conn, user["id"], limit=20)
    return [public_advance(conn, r, user) for r in rows]


def approve_advance(conn: sqlite3.Connection, adv_id: int, source: str, custodian: str, user: User) -> dict[str, Any]:
    need(source in ADVANCE_SOURCES, "اختر مصدر الصرف", "source")
    custodian = (custodian or "").strip()
    if source == "1104":
        need(custodian, "اكتب صاحب العهدة", "custodian")
        need(custodian in settings_service.party_names(conn, "custodian"), "صاحب العهدة غير موجود في قائمة الأطراف", "custodian")
    with transaction(conn):
        r = requests_repo.get_advance(conn, adv_id)
        if not r:
            raise NotFound("الطلب غير موجود")
        if r["status"] != "pending":
            raise Conflict("الطلب لم يعد بانتظار الموافقة")
        if not can_approve_advance(user, r):
            raise Forbidden("لا يمكنك اعتماد هذا الطلب")
        memo = f"سلفة للعامل {r['employee']}" + (f" – {r['reason']}" if r["reason"] else "")
        if r["installments"] > 1:
            memo += f" (تُخصم على {r['installments']} دفعات)"
        maker = {"id": r["created_by"], "label": r["created_by_label"]}
        res = ledger_service.post(conn, {
            "date": today(), "memo": memo, "src": "out", "ref": f"ADV-{r['id']}", "party": r["employee"],
            "lines": [{"a": "1106", "d": r["amount"], "party": r["employee"]},
                      {"a": source, "c": r["amount"], "party": custodian if source == "1104" else None}],
            "meta": {"advanceId": r["id"], "maker": r["created_by_label"], "checker": user["label"]},
        }, maker, approver=user)
        requests_repo.decide_advance(conn, r["id"], "approved", user["id"], user["label"], now_iso(), res["no"])
    return res


def reject_advance(conn: sqlite3.Connection, adv_id: int, user: User) -> None:
    with transaction(conn):
        r = requests_repo.get_advance(conn, adv_id)
        if not r:
            raise NotFound("الطلب غير موجود")
        if r["status"] != "pending":
            raise Conflict("الطلب لم يعد بانتظار الموافقة")
        if not can_approve_advance(user, r):
            raise Forbidden("لا يمكنك رفض هذا الطلب")
        requests_repo.decide_advance(conn, r["id"], "rejected", user["id"], user["label"], now_iso())


def public_advance(conn: sqlite3.Connection, r: dict[str, Any], user: User) -> dict[str, Any]:
    out = {
        "id": r["id"], "employee": r["employee"], "amount": r["amount"], "installments": r["installments"],
        "reason": r["reason"], "status": r["status"], "createdByLabel": r["created_by_label"], "createdAt": r["created_at"],
        "decidedByLabel": r["decided_by_label"], "entryNo": r["entry_no"],
        "canDecide": r["status"] == "pending" and can_approve_advance(user, r),
    }
    # §6.1: the approver sees the employee's current advance balance. Supervisors never see money balances.
    if out["canDecide"] or access.sees_finance(user):
        out["balance"] = ledger_service.pbal(conn, "1106", r["employee"])["y"]
    return out


def employee_names(conn: sqlite3.Connection) -> list[str]:
    return requests_repo.employee_names(conn)


def pending_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {"requests": requests_repo.pending_requests(conn), "advances": requests_repo.pending_advances(conn)}

