"""Logins created by the owner, password hashing and sessions (spec §14).

Passwords are hashed with the standard library's scrypt. Session tokens are random,
sent to the browser in an HttpOnly cookie, and only their SHA-256 hash is stored.
"""

import hashlib
import hmac
import logging
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from config import settings
from database import transaction
from repositories import users_repo
from services.chart import ROLES
from utils.dates import now_iso
from utils.errors import Conflict, DomainError, NotFound, need

logger = logging.getLogger(__name__)

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}
MAX_FAILED = 5
LOCK_MINUTES = 15
MIN_PASSWORD = 8


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        check = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), dklen=32, n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(check.hex(), digest)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def public_user(u: dict[str, Any]) -> dict[str, Any]:
    return {"id": u["id"], "username": u["username"], "label": u["label"], "role": u["role"],
            "roleLabel": ROLES.get(u["role"], u["role"]), "approver": bool(u["approver"]), "active": bool(u["active"])}


# ---- bootstrap ----

def ensure_owner(conn: sqlite3.Connection, username: str, password: str, label: str) -> None:
    """Create the first owner from the environment, once."""
    if users_repo.owner_exists(conn):
        return
    if not username or not password:
        logger.warning("No owner account exists. Set OWNER_USERNAME and OWNER_PASSWORD to create one.")
        return
    need(len(password) >= MIN_PASSWORD, "كلمة مرور المالك قصيرة")
    with transaction(conn):
        users_repo.create(conn, username, label or username, hash_password(password), "owner", True, now_iso())
    logger.info("Created owner account %s", username)


# ---- login / sessions ----

def login(conn: sqlite3.Connection, username: str, password: str) -> tuple[str, dict[str, Any]]:
    """Returns (session token, user). Locks the account for 15 minutes after 5 failures."""
    bad = DomainError("اسم المستخدم أو كلمة المرور غير صحيحة")
    username = (username or "").strip()
    u = users_repo.get_auth_by_username(conn, username)
    if not u or not u["active"]:
        hash_password(password or "x")  # spend the same time as a real check
        raise bad
    now = datetime.now(timezone.utc)
    if u["locked_until"] and u["locked_until"] > _utc(now):
        raise DomainError("الحساب موقوف مؤقتاً بعد محاولات خاطئة. حاول بعد ربع ساعة.")
    if not verify_password(password or "", u["password_hash"]):
        with transaction(conn):
            failed = u["failed_logins"] + 1
            users_repo.update(conn, u["id"], failed_logins=failed,
                              locked_until=_utc(now + timedelta(minutes=LOCK_MINUTES)) if failed >= MAX_FAILED else None)
        raise bad
    token = secrets.token_urlsafe(32)
    with transaction(conn):
        users_repo.update(conn, u["id"], failed_logins=0, locked_until=None)
        users_repo.delete_expired_sessions(conn, _utc(now))
        users_repo.create_session(conn, _token_hash(token), u["id"], _utc(now),
                                  _utc(now + timedelta(days=settings.session_days)))
    return token, public_user(u)


def user_for_token(conn: sqlite3.Connection, token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    h = _token_hash(token)
    s = users_repo.get_session(conn, h)
    now = datetime.now(timezone.utc)
    if not s or s["expires_at"] < _utc(now):
        return None
    u = users_repo.get_by_id(conn, s["user_id"])
    if not u or not u["active"]:
        return None
    # Sliding expiry: extend at most once a day.
    new_exp = _utc(now + timedelta(days=settings.session_days))
    if new_exp[:10] > s["expires_at"][:10]:
        with transaction(conn):
            users_repo.extend_session(conn, h, new_exp)
    return public_user(u)


def logout(conn: sqlite3.Connection, token: str | None) -> None:
    if token:
        with transaction(conn):
            users_repo.delete_session(conn, _token_hash(token))


def change_own_password(conn: sqlite3.Connection, user_id: int, current: str, new: str) -> None:
    u = users_repo.get_by_id(conn, user_id)
    auth = users_repo.get_auth_by_username(conn, u["username"])
    need(verify_password(current or "", auth["password_hash"]), "كلمة المرور الحالية غير صحيحة", "current")
    need(len(new or "") >= MIN_PASSWORD, f"كلمة المرور الجديدة {MIN_PASSWORD} أحرف على الأقل", "new")
    with transaction(conn):
        users_repo.update(conn, user_id, password_hash=hash_password(new))


# ---- user management (owner) ----

def list_users(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [public_user(u) for u in users_repo.list_all(conn)]


def _check_role(role: str) -> None:
    need(role in ("entry", "reviewer", "supervisor", "none"), "الدور غير صحيح", "role")


def create_user(conn: sqlite3.Connection, username: str, label: str, password: str, role: str, approver: bool) -> dict[str, Any]:
    username = (username or "").strip()
    need(3 <= len(username) <= 40 and " " not in username, "اسم المستخدم من 3 إلى 40 حرفاً بلا مسافات", "username")
    need(len(password or "") >= MIN_PASSWORD, f"كلمة المرور {MIN_PASSWORD} أحرف على الأقل", "password")
    _check_role(role)
    approver = bool(approver) and role in ("entry", "reviewer")
    with transaction(conn):
        if users_repo.get_auth_by_username(conn, username):
            raise Conflict("اسم المستخدم مستخدم من قبل", "username")
        uid = users_repo.create(conn, username, (label or username).strip(), hash_password(password), role, approver, now_iso())
    return public_user(users_repo.get_by_id(conn, uid))


def update_user(conn: sqlite3.Connection, user_id: int, changes: dict[str, Any]) -> dict[str, Any]:
    u = users_repo.get_by_id(conn, user_id)
    if not u:
        raise NotFound("المستخدم غير موجود")
    need(u["role"] != "owner", "لا يمكن تعديل حساب المالك من هنا")
    fields: dict[str, Any] = {}
    if "label" in changes and changes["label"] is not None:
        fields["label"] = str(changes["label"]).strip() or u["label"]
    role = changes.get("role") or u["role"]
    if "role" in changes and changes["role"] is not None:
        _check_role(role)
        fields["role"] = role
    if "approver" in changes and changes["approver"] is not None:
        fields["approver"] = int(bool(changes["approver"]) and role in ("entry", "reviewer"))
    elif "role" in fields and role not in ("entry", "reviewer"):
        fields["approver"] = 0
    if "active" in changes and changes["active"] is not None:
        fields["active"] = int(bool(changes["active"]))
    if changes.get("password"):
        need(len(changes["password"]) >= MIN_PASSWORD, f"كلمة المرور {MIN_PASSWORD} أحرف على الأقل", "password")
        fields["password_hash"] = hash_password(changes["password"])
        fields["failed_logins"] = 0
        fields["locked_until"] = None
    with transaction(conn):
        users_repo.update(conn, user_id, **fields)
        if fields.get("active") == 0 or "password_hash" in fields or "role" in fields:
            users_repo.delete_user_sessions(conn, user_id)
    return public_user(users_repo.get_by_id(conn, user_id))


def has_other_approver(conn: sqlite3.Connection, user_id: int) -> bool:
    return users_repo.other_approvers(conn, user_id) > 0

