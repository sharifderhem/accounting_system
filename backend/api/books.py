"""Read-only views for owner and reviewer (home, analytics, journal, reports, reconciliation)
and the owner's postings launched from them."""

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Query

from api.deps import finance_viewer, get_conn, owner
from schemas.requests import BudgetSave, CreditLimits, DateOnly, FxClose, ReconSave
from schemas.responses import PostedRef
from services import (
    adjustments_service, analytics_service, home_service, journal_service, ledger_service, recon_service, reports,
    settings_service,
)
from services.reports import operations

router = APIRouter(prefix="/api", tags=["books"])


@router.get("/home")
def home(_: dict[str, Any] = Depends(finance_viewer), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return home_service.overview(conn)


@router.get("/analytics")
def analytics(period: str = "week", _: dict[str, Any] = Depends(finance_viewer),
              conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return analytics_service.overview(conn, period)


@router.get("/journal")
def journal(frm: str = "", to: str = "", src: str = "", party: str = "", account: str = "", cur: str = "", q: str = "",
            limit: int = Query(60, ge=1, le=5000), offset: int = Query(0, ge=0),
            _: dict[str, Any] = Depends(finance_viewer), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    filters = {"frm": frm, "to": to, "src": src, "party": party, "account": account, "cur": cur, "q": q}
    return journal_service.search(conn, filters, limit, offset)


@router.post("/entries/{entry_id}/reverse", response_model=PostedRef)
def reverse(entry_id: int, user: dict[str, Any] = Depends(owner), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return ledger_service.reverse(conn, entry_id, user)


@router.get("/reports/{kind}")
def report(kind: str, frm: str | None = None, to: str | None = None, party: str | None = None, account: str | None = None,
           cur: str = "", month: str | None = None, horizon: int | None = None, cartons: float | None = None,
           _: dict[str, Any] = Depends(finance_viewer), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    params = {"frm": frm or None, "to": to or None, "party": party, "account": account, "cur": cur, "month": month,
              "horizon": horizon, "cartons": cartons}
    return reports.run(conn, kind, params)


# ---- owner postings from reports (§11) ----

@router.put("/reports/aging/limits")
def credit_limits(body: CreditLimits, _: dict[str, Any] = Depends(owner), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    settings_service.set_credit_limits(conn, body.limits)
    return reports.run(conn, "aging", {})


@router.post("/reports/aging/provision", response_model=PostedRef)
def provision(body: DateOnly, user: dict[str, Any] = Depends(owner), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return adjustments_service.post_provision(conn, body.date, user)


@router.post("/reports/fxpos/revalue", response_model=PostedRef)
def revalue(user: dict[str, Any] = Depends(owner), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return adjustments_service.revalue(conn, user)


@router.post("/reports/zakat/post", response_model=PostedRef)
def zakat(body: DateOnly, user: dict[str, Any] = Depends(owner), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return adjustments_service.post_zakat(conn, body.date, user)


@router.put("/reports/budget")
def budget(body: BudgetSave, _: dict[str, Any] = Depends(owner), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return operations.save_budget(conn, body.month, body.values)


# ---- reconciliation (§10) ----

@router.get("/recon/checks")
def checks(_: dict[str, Any] = Depends(finance_viewer), conn: sqlite3.Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    return recon_service.checks(conn)


@router.get("/recon/statement")
def statement(key: str = "1103", _: dict[str, Any] = Depends(finance_viewer),
              conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return recon_service.statement(conn, key)


@router.put("/recon/statement")
def save_statement(body: ReconSave, user: dict[str, Any] = Depends(owner), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return recon_service.save(conn, body.key, body.lineIds, body.date, body.statement, user)


@router.post("/recon/fx-close", response_model=PostedRef)
def fx_close(body: FxClose, user: dict[str, Any] = Depends(owner), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return adjustments_service.close_fx_difference(conn, body.party, user)
