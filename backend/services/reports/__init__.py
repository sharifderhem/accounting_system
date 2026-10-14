"""The 17 reports of spec §11, as structured data. The frontend lays them out."""

import sqlite3
from typing import Any, Callable

from services.reports import customers, operations, statements
from utils.errors import NotFound

REPORTS: dict[str, tuple[str, Callable[..., dict[str, Any]]]] = {
    "claim": ("مطالبة مالية", customers.claim),
    "tb": ("ميزان المراجعة", statements.trial_balance),
    "is": ("قائمة الدخل", statements.income_statement),
    "party": ("كشف حساب طرف", statements.party_statement),
    "ledger": ("دفتر الأستاذ", statements.account_ledger),
    "cost": ("تكلفة الإنتاج", operations.production_cost),
    "cash": ("التدفق النقدي", operations.cash_forecast),
    "aging": ("مخاطر العملاء", customers.aging),
    "fxrisk": ("مخاطر العملة", operations.fx_risk),
    "be": ("نقطة التعادل", operations.break_even),
    "budget": ("الموازنة", operations.budget),
    "eff": ("الكفاءة والتوقف", operations.efficiency),
    "cc": ("مراكز التكلفة", statements.cost_centers),
    "fxpos": ("مركز العملة", customers.currency_position),
    "vat": ("الضريبة", statements.vat),
    "zakat": ("الزكاة", statements.zakat),
    "inv": ("المخزون", statements.inventory),
}


def run(conn: sqlite3.Connection, kind: str, params: dict[str, Any]) -> dict[str, Any]:
    if kind not in REPORTS:
        raise NotFound("التقرير غير موجود")
    title, fn = REPORTS[kind]
    data = fn(conn, **params)
    return {"kind": kind, "title": title, **data}
