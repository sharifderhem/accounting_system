"""Home screen (spec §12.1): balances, KPIs and alerts for the owner and reviewer."""

import sqlite3
from typing import Any

from repositories import assets_repo, entries_repo, requests_repo, shifts_repo
from services import ledger_service, settings_service
from services.chart import STOCK_ACCOUNTS, acc_name, acc_unit
from services.costing import chiller_kwh
from services.rates_service import PLANNED_MACHINE_KWH_DAY, stock_days
from utils.dates import today
from utils.money import r2


def _f(x: float, d: int = 0) -> str:
    return f"{x:,.{d}f}"


def overview(conn: sqlite3.Connection) -> dict[str, Any]:
    s = settings_service.get(conn)
    fx = s["fx"]
    bal = lambda a: ledger_service.bal(conn, a)  # noqa: E731
    b1, b2, b3, pw = bal("1101"), bal("1102"), bal("1103"), bal("1401")
    wallets = {a: bal(a)["y"] for a in ("1107", "1108", "1109")}

    def party_rows(account: str, use_fc: bool) -> list[dict[str, Any]]:
        out = []
        for p in ledger_service.parties_on(conn, account):
            b = ledger_service.pbal(conn, account, p)
            if (use_fc and abs(b["fc"]) > 0.5) or abs(b["y"]) > 1:
                out.append({"party": p, "sar": b["fc"], "yer": b["y"]})
        return out

    customers = party_rows("1201", True)
    custody = [r for r in party_rows("1104", False) if abs(r["yer"]) > 1]
    advances = [r for r in party_rows("1106", False) if abs(r["yer"]) > 1]

    recent = [x for x in shifts_repo.list_all(conn, status="approved", limit=14) if x.get("cost")]
    cost_total = sum(x["cost"].get("total") or 0 for x in recent)
    cartons = sum(x["cartons"] or 0 for x in recent)
    if recent:
        elec_day = sum(x["cost"].get("kwh") or 0 for x in recent) / len(recent) * (24 / s["shiftHours"]) * s["kwhPrice"]
    else:
        elec_day = (PLANNED_MACHINE_KWH_DAY + chiller_kwh(s, 24)) * s["kwhPrice"]
    power_days = pw["y"] / elec_day if pw["y"] > 0 else 0
    per_sar = cost_total / cartons / fx if cartons else None
    eff = sum(x["cost"].get("eff") or 0 for x in recent) / len(recent) * 100 if recent else None

    month_start = today()[:8] + "01"
    sales = -entries_repo.sums(conn, account="4101", since=month_start)["y"]
    cogs = entries_repo.sums(conn, account="5101", since=month_start)["y"]

    days = stock_days(conn, s)
    stock = []
    for a in STOCK_ACCOUNTS:
        b = bal(a)
        stock.append({"account": a, "name": acc_name(a), "qty": b["q"], "unit": acc_unit(a), "value": b["y"],
                      "avg": r2(b["y"] / b["q"]) if b["q"] > 0 else None, "days": r2(max(0, days[a])) if days.get(a) is not None else None})

    alerts: list[dict[str, str]] = []

    def alert(level: str, text: str) -> None:
        alerts.append({"level": level, "text": text})

    if b3["y"] < 0:
        alert("info", f"الحساب اليمني مسحوب على المكشوف بـ {_f(-b3['y'])} ر.ي. الصرّاف يسمح بالمكشوف اليمني بشرط استمرار الحركة على الحساب.")
    if b2["fc"] < 0:
        alert("bad", f"رصيد الحساب السعودي سالب ({_f(b2['fc'])} ر.س) والصرّاف لا يكشف بالسعودي؛ راجع الحوالات أو طابق الرصيد الفعلي.")
    for r in custody:
        alert("warn", f"عهدة {r['party']}: {_f(r['yer'])} ر.ي غير مصفّاة. سجّل مصروفاتها أو طابق الرصيد.")
    pending_shifts = shifts_repo.pending_count(conn)
    if pending_shifts:
        alert("warn", f"{pending_shifts} وردية بانتظار الاعتماد في تبويب «الورديات».")
    pending_req = requests_repo.pending_requests(conn) + requests_repo.pending_advances(conn)
    if pending_req:
        alert("warn", f"{pending_req} طلب صرف أو سلفة بانتظار الموافقة في تبويب «الطلبات».")
    for row in stock:
        if row["qty"] < -0.01:
            alert("bad", f"رصيد {row['name']} سالب ({_f(row['qty'])} {row['unit']}). سجّل المشتريات أو جرداً فعلياً.")
    min_days = float(s.get("minStockDays") or 3)
    for a in ("1301", "1302", "1303"):
        d = days.get(a)
        if d is not None and d < min_days:
            alert("bad" if d < 1 else "warn",
                  f"{acc_name(a)} يكفي نحو {_f(max(0, d), 1)} يوم فقط بمعدل الاستهلاك الحالي. وقت الشراء.")
    unpriced = [a["name"] for a in assets_repo.list_all(conn) if not a["cost"]]
    if unpriced:
        alert("warn", f"أصول بلا سعر: {'، '.join(unpriced)}. إهلاكها غير محسوب في تكلفة الكرتون؛ أدخل أسعارها من تبويب «الأصول» عندما تعرفها.")
    if not recent:
        alert("warn", "لا توجد ورديات معتمدة بعد. احتساب التكلفة الفعلية للكرتون يبدأ من أول وردية تُعتمد، ويُفضَّل تسجيل جرد افتتاحي للمخزون أولاً.")
    if pw["y"] > 0 and power_days < 5:
        alert("bad", f"رصيد الكهرباء المقدم يكفي نحو {_f(power_days, 1)} يوم فقط.")

    return {
        "today": today(), "fx": fx, "priceSar": s["priceSar"],
        "balances": {
            "cash": b1["y"], "sar": b2["fc"], "sarAvgRate": r2(b2["y"] / b2["fc"]) if b2["fc"] else None, "yer": b3["y"],
            "wallets": wallets, "walletsTotal": r2(sum(wallets.values())), "power": pw["y"], "powerDays": r2(power_days),
            "customersSar": r2(sum(c["sar"] for c in customers)),
        },
        "kpis": {
            "efficiency": r2(eff) if eff is not None else None, "shifts": len(recent),
            "costPerCartonSar": r2(per_sar) if per_sar else None, "marginSar": r2(s["priceSar"] - per_sar) if per_sar else None,
            "monthSalesYer": r2(sales), "monthSalesSar": r2(sales / fx), "monthGrossYer": r2(sales - cogs),
            "monthGrossSar": r2((sales - cogs) / fx),
        },
        "customers": customers, "custody": custody, "advances": advances, "stock": stock, "alerts": alerts,
        "recentShifts": [{"date": x["date"], "shift": x["shift"], "cartons": x["cartons"], "rmKg": x["cost"].get("rmKg"),
                          "kwh": x["cost"].get("kwh"), "total": x["cost"].get("total"), "perSar": x["cost"].get("perSar"),
                          "marginSar": r2(s["priceSar"] - (x["cost"].get("perSar") or 0))} for x in recent[:6]],
    }
