"""Fixed assets and straight-line depreciation (spec §8)."""

import secrets
import sqlite3
from typing import Any

from database import transaction
from repositories import assets_repo, entries_repo
from services import access, ledger_service, settings_service
from services.costing import asset_active, asset_daily, asset_end, dep_daily
from services.rates_service import production_rates
from utils.dates import days_between, is_iso, next_day, prev_day, today
from utils.errors import DomainError, NotFound, need
from utils.money import is_num, r2

User = dict[str, Any]
FUNDING = ("3101", "1103", "1102", "2102")
CURRENCIES = ("USD", "SAR", "YER")


def to_yer(s: dict[str, Any], amount: float, cur: str) -> float:
    if cur == "USD":
        return r2(amount * s["usdSar"] * s["fx"])
    if cur == "SAR":
        return r2(amount * s["fx"])
    return r2(amount)


def accumulated(conn: sqlite3.Connection, asset_id: str) -> float:
    return -entries_repo.sums(conn, account="1502", asset=asset_id)["y"]


def overview(conn: sqlite3.Connection) -> dict[str, Any]:
    s = settings_service.get(conn)
    assets = assets_repo.list_all(conn)
    rows = []
    for a in sorted(assets, key=lambda x: -(x["cost"] or 0)):
        acc = accumulated(conn, a["id"])
        monthly = asset_daily(a) * 365 / 12 if a["cost"] else 0
        rows.append({
            "id": a["id"], "name": a["name"], "date": a["date"], "cost": a["cost"], "amount": a["amount"], "cur": a["cur"],
            "life": a["life"], "salvage": a["salvage"], "cc": a["cc"], "note": a["note"], "postedTo": a["posted_to"],
            "endDate": asset_end(a), "active": asset_active(a, today()), "monthly": r2(monthly), "accumulated": acc,
            "bookValue": r2(a["cost"] - acc) if a["cost"] else None, "priced": a["cost"] > 0,
        })
    daily = dep_daily(assets, today())
    rates = production_rates(conn, s)
    return {
        "assets": rows,
        "totals": {
            "cost": r2(sum(a["cost"] for a in assets)),
            "monthly": r2(sum(r["monthly"] for r in rows)),
            "accumulated": r2(sum(r["accumulated"] for r in rows)),
            "perCartonSar": r2(daily / (rates["car"] or 1) / s["fx"]),
            "cartonsPerDay": rates["car"],
            "absorbed": r2(-entries_repo.sums(conn, account="5205", side="c")["y"]),
        },
    }


def _acquire(conn: sqlite3.Connection, s: dict[str, Any], a: dict[str, Any], amount: float, cur: str, fund: str, user: User) -> float:
    cost = to_yer(s, amount, cur)
    if fund == "1102":
        credit = {"a": "1102", "c": cost, "cur": "SAR", "fc": amount if cur == "SAR" else r2(cost / s["fx"])}
    else:
        credit = {"a": fund, "c": cost, "party": settings_service.owner_name(conn) if fund == "3101" else None}
    unit = {"USD": "دولار", "SAR": "ر.س", "YER": "ر.ي"}[cur]
    ledger_service.post(conn, {
        "date": a["date"], "memo": f"إثبات أصل: {a['name']} ({amount:,.0f} {unit})", "src": "manual", "ref": "ASSET",
        "lines": [{"a": "1501", "d": cost, "asset": a["id"], "cc": a.get("cc") or "prod"}, credit],
        "meta": {"assetAcquired": a["id"]},
    }, user)
    return cost


def add(conn: sqlite3.Connection, form: dict[str, Any], user: User) -> dict[str, Any]:
    access.require_owner(user)
    s = settings_service.get(conn)
    name, date = str(form.get("name") or "").strip(), str(form.get("date") or "")
    amount, life = form.get("amount") or 0, form.get("life")
    salvage, cur, fund = form.get("salvage") or 0, form.get("cur") or "YER", form.get("fund") or "3101"
    cc = form.get("cc") or "prod"
    need(name, "اكتب اسم الأصل", "name")
    need(is_iso(date), "اختر تاريخ الشراء", "date")
    need(is_num(amount) and amount >= 0, "السعر غير صحيح", "amount")
    need(is_num(life) and life > 0, "العمر الإنتاجي بالسنوات أكبر من صفر", "life")
    need(is_num(salvage) and salvage >= 0, "القيمة المتبقية غير صحيحة", "salvage")
    need(cur in CURRENCIES, "العملة غير صحيحة", "cur")
    need(fund in FUNDING, "اختر مصدر التمويل", "fund")
    need(cc in settings_service.cc_ids(conn), "مركز التكلفة غير معروف", "cc")
    a = {"id": "as" + secrets.token_hex(5), "name": name, "date": date, "life": float(life), "salvage": float(salvage),
         "cc": cc, "note": str(form.get("note") or ""), "posted_to": prev_day(date), "created_at": today(),
         "amount": float(amount), "cur": cur, "cost": 0}
    with transaction(conn):
        assets_repo.insert(conn, a)
        if amount > 0:
            cost = _acquire(conn, s, a, float(amount), cur, fund, user)
            need(salvage < cost, "القيمة المتبقية أكبر من التكلفة", "salvage")
            assets_repo.update(conn, a["id"], cost=cost)
    return assets_repo.get(conn, a["id"])


def set_price(conn: sqlite3.Connection, asset_id: str, form: dict[str, Any], user: User) -> dict[str, Any]:
    """§8: an asset entered without a price gets one later; that posts the acquisition."""
    access.require_owner(user)
    s = settings_service.get(conn)
    amount, cur, fund = form.get("amount"), form.get("cur") or "USD", form.get("fund") or "3101"
    need(is_num(amount) and amount > 0, "اكتب السعر", "amount")
    need(cur in CURRENCIES, "العملة غير صحيحة", "cur")
    need(fund in FUNDING, "اختر مصدر التمويل", "fund")
    with transaction(conn):
        a = assets_repo.get(conn, asset_id)
        if not a:
            raise NotFound("الأصل غير موجود")
        need(not a["cost"], "الأصل مسعّر مسبقاً")
        life = form.get("life")
        if is_num(life) and life > 0:
            a["life"] = float(life)
        cost = _acquire(conn, s, a, float(amount), cur, fund, user)
        assets_repo.update(conn, asset_id, cost=cost, amount=float(amount), cur=cur, life=a["life"], posted_to=prev_day(a["date"]))
    return assets_repo.get(conn, asset_id)


def set_life(conn: sqlite3.Connection, asset_id: str, life: float, user: User) -> dict[str, Any]:
    access.require_owner(user)
    need(is_num(life) and life > 0, "العمر الإنتاجي بالسنوات أكبر من صفر", "life")
    with transaction(conn):
        a = assets_repo.get(conn, asset_id)
        if not a:
            raise NotFound("الأصل غير موجود")
        assets_repo.update(conn, asset_id, life=float(life), note=f"العمر عُدّل إلى {life:g} سنة في {today()}")
    return assets_repo.get(conn, asset_id)


def post_depreciation(conn: sqlite3.Connection, to: str, user: User) -> dict[str, Any]:
    """§8 monthly posting: for each asset, from the day after ``posted_to`` up to ``to``."""
    access.require_owner(user)
    need(is_iso(to), "اختر التاريخ", "to")
    need(to <= today(), "لا يُرحَّل إهلاك لتاريخ مستقبلي", "to")
    with transaction(conn):
        lines, items = [], []
        for a in assets_repo.list_all(conn):
            if not a["cost"]:
                continue
            start = next_day(a["posted_to"] or prev_day(a["date"]))
            end = min(to, asset_end(a))
            if start > end:
                continue
            days = days_between(start, end) + 1
            amount = r2(asset_daily(a) * days)
            if amount <= 0:
                continue
            lines += [{"a": "5205", "d": amount, "cc": a["cc"] or "prod", "memo": f"إهلاك {a['name']} {days} يوم"},
                      {"a": "1502", "c": amount, "asset": a["id"], "memo": a["name"]}]
            items.append({"asset": a["id"], "prev": a["posted_to"], "to": end})
        if not lines:
            raise DomainError("الإهلاك مُرحّل حتى هذا التاريخ")
        res = ledger_service.post(conn, {"date": to, "memo": f"إهلاك الأصول حتى {to}", "src": "manual", "ref": f"DEP-{to}",
                                         "lines": lines, "meta": {"depreciation": items}}, user)
        for item in items:
            assets_repo.update(conn, item["asset"], posted_to=item["to"])
    return res
