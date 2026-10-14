"""Who may do what (spec §14). Every API route checks these on the server."""

from typing import Any

from utils.errors import Forbidden

User = dict[str, Any]

# Transaction forms per role. Owner-only forms: fx, xfer, adj, count, manual.
ENTRY_FORMS = ("sale", "in", "out", "exp")
OWNER_FORMS = ("sale", "in", "out", "exp", "fx", "xfer", "adj", "count", "manual")


def is_owner(u: User) -> bool:
    return u["role"] == "owner"


def is_approver(u: User) -> bool:
    """The owner always approves; entry and reviewer users can be flagged as approvers."""
    return u["role"] == "owner" or (bool(u.get("approver")) and u["role"] in ("entry", "reviewer"))


def sees_finance(u: User) -> bool:
    """Balances, reports, journal, analytics, reconciliation."""
    return u["role"] in ("owner", "reviewer")


def forms_for(u: User) -> tuple[str, ...]:
    if u["role"] == "owner":
        return OWNER_FORMS
    if u["role"] == "entry":
        return ENTRY_FORMS
    return ()


def can_submit_shift(u: User) -> bool:
    return u["role"] in ("owner", "supervisor")


def can_request_advance(u: User) -> bool:
    return u["role"] in ("owner", "entry", "reviewer", "supervisor")


def require_owner(u: User) -> None:
    if not is_owner(u):
        raise Forbidden("هذه العملية للمالك فقط")


def require_finance(u: User) -> None:
    if not sees_finance(u):
        raise Forbidden("ليست لديك صلاحية عرض الأرقام المالية")


def require_form(u: User, kind: str) -> None:
    if kind not in forms_for(u):
        raise Forbidden("ليست لديك صلاحية تسجيل هذا النوع من الحركات")
