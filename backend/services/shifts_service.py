"""Production shifts and absorption costing (spec §7)."""

import sqlite3
from typing import Any

from database import transaction
from repositories import assets_repo, entries_repo, shifts_repo
from services import access, ledger_service, settings_service
from services.chart import DOWN_REASONS, ELECTRICITY_STATION, SHIFTS
from services.costing import (
    cartons_per_minute, chiller_kwh, dep_daily, max_cartons_shift, pig_kg_cost, pigment_kg_for, rm_kg_cost,
    with_labor_delta,
)
from utils.dates import is_iso, now_iso
from utils.errors import Conflict, DomainError, Forbidden, NotFound, need
from utils.money import is_num, r2

User = dict[str, Any]


def _fmt(x: float, d: int = 0) -> str:
    return f"{x:,.{d}f}"


# ---------------------------------------------------------------- submit (§7.1)

def submit(conn: sqlite3.Connection, form: dict[str, Any], user: User) -> dict[str, Any]:
    if not access.can_submit_shift(user):
        raise Forbidden("ليست لديك صلاحية تسجيل الورديات")

    def n(key: str) -> float | None:
        v = form.get(key)
        return float(v) if is_num(v) else None

    date, shift = str(form.get("date") or ""), form.get("shift")
    m1, m2, bags, cartons = n("meterStart"), n("meterEnd"), n("bags"), n("cartons")
    need(is_iso(date), "اختر التاريخ", "date")
    need(shift in SHIFTS, "اختر الوردية", "shift")
    need(m1 is not None and m1 >= 0, "اكتب قراءة العداد قبل", "meterStart")
    need(m2 is not None and m1 is not None and m2 > m1, "قراءة العداد بعد يجب أن تكون أكبر من قبل", "meterEnd")
    need(bags is not None and bags >= 0, "اكتب عدد الأكياس المفتوحة", "bags")
    need(cartons is not None and cartons > 0, "اكتب عدد الكراتين المعبأة", "cartons")
    scrap = n("scrapKg") or 0
    need(scrap >= 0, "التالف لا يكون سالباً", "scrapKg")
    down = n("downMin") or 0
    need(down >= 0, "دقائق التوقف لا تكون سالبة", "downMin")
    reason = str(form.get("downReason") or "")
    need(reason == "" or reason in DOWN_REASONS, "سبب التوقف غير صحيح", "downReason")
    s1, s2 = n("shotsStart"), n("shotsEnd")
    if s1 is not None and s2 is not None:
        need(s2 >= s1, "عداد الضربات بعد يجب أن يكون أكبر من قبل", "shotsEnd")
    with transaction(conn):
        if shifts_repo.slot_taken(conn, date, shift):
            raise Conflict(f"وردية {shift} بتاريخ {date} مسجلة مسبقاً.", "shift")
        shift_id = shifts_repo.insert(conn, {
            "date": date, "shift": shift, "by_name": str(form.get("byName") or "").strip() or user["label"],
            "meter_start": m1, "meter_end": m2, "bags": bags, "extra_kg": n("extraKg") or 0, "cartons": cartons,
            "scrap_kg": scrap, "shots_start": s1, "shots_end": s2, "down_min": down, "down_reason": reason,
            "notes": str(form.get("notes") or "").strip(), "created_by": user["id"], "created_at": now_iso(),
        })
    return public(shifts_repo.get(conn, shift_id), with_cost=False)


def last_meter(conn: sqlite3.Connection) -> float | None:
    return shifts_repo.last_meter_end(conn)


# ---------------------------------------------------------------- cost (§7.2)

def shift_cost(conn: sqlite3.Connection, sh: dict[str, Any]) -> dict[str, Any]:
    s = settings_service.get(conn)
    date = sh["date"]
    kwh_meter = max(0.0, (sh["meter_end"] or 0) - (sh["meter_start"] or 0))
    kwh_chiller = r2(chiller_kwh(s, s["shiftHours"]))
    kwh = r2(kwh_meter + kwh_chiller)
    elec = r2(kwh * s["kwhPrice"])
    rm_kg = r2((sh["bags"] or 0) * s["bagKg"] + (sh["extra_kg"] or 0))
    rm_avg = ledger_service.avg_cost(conn, "1301", rm_kg_cost(s), date)
    rm_cost = r2(rm_kg * rm_avg)
    pig_kg = r2(pigment_kg_for(s, rm_kg) * 1000) / 1000
    pig_avg = ledger_service.avg_cost(conn, "1302", pig_kg_cost(s), date)
    pig_cost = r2(pig_kg * pig_avg)
    cartons = sh["cartons"] or 0
    ct_avg = ledger_service.avg_cost(conn, "1303", s["cartonCost"], date)
    ct_cost = r2(cartons * ct_avg)
    labor = r2(max(0.0, entries_repo.sums(conn, account="5201", on=date, shift=sh["shift"])["y"]))
    dep = r2(dep_daily(assets_repo.list_all(conn), date) * s["shiftHours"] / 24)
    total = r2(elec + rm_cost + pig_cost + ct_cost + labor + dep)
    per = total / cartons if cartons else 0
    prod_kg = cartons * s["cartonNetKg"]
    mat_per_carton = rm_kg / cartons if cartons else 0
    shots = (sh["shots_end"] or 0) - (sh["shots_start"] or 0)
    exp_cartons = shots * s["cavities"] / s["capsPerCarton"] if shots > 0 else None
    max_cartons = max_cartons_shift(s)
    down_min = min(sh["down_min"] or 0, s["shiftHours"] * 60)
    run_min = s["shiftHours"] * 60 - down_min
    cpm = cartons_per_minute(s)
    eff = cartons / max_cartons if max_cartons else 0
    perf = cartons / (run_min * cpm) if run_min else 0
    lost_down = down_min * cpm
    lost_other = max(0.0, max_cartons - cartons - lost_down)

    flags: list[str] = []
    if not cartons:
        flags.append("لم تُسجَّل كراتين منتجة")
    if eff and eff < 0.75:
        tail = (f" (توقف {_fmt(down_min)} دقيقة: {sh['down_reason'] or 'بدون سبب'})" if down_min
                else " دون تسجيل توقف — راجع سرعة الدورة أو الفتحات المغلقة")
        flags.append(f"الكفاءة {_fmt(eff * 100)}% من الطاقة القصوى{tail}")
    if cartons and rm_kg:
        dev = (mat_per_carton - s["cartonNetKg"]) / s["cartonNetKg"]
        if dev > s["normalScrapPct"] / 100:
            flags.append(f"استهلاك المواد {_fmt(mat_per_carton, 2)} كغ للكرتون، أعلى من الصافي {s['cartonNetKg']:g} بنسبة {_fmt(dev * 100, 1)}%")
        if dev < -0.03:
            flags.append(f"المواد المسجلة {_fmt(rm_kg)} كغ أقل من وزن الإنتاج {_fmt(prod_kg)} كغ؛ راجع عدد الأكياس")
    scrap = sh["scrap_kg"] or 0
    if scrap > 0 and rm_kg and scrap / rm_kg > s["normalScrapPct"] / 100:
        flags.append(f"التالف {_fmt(scrap)} كغ = {_fmt(scrap / rm_kg * 100, 1)}% من المواد")
    if exp_cartons and cartons and abs(exp_cartons - cartons) / exp_cartons > 0.05:
        flags.append(f"العداد يعطي {_fmt(exp_cartons, 1)} كرتون والمسجل {_fmt(cartons)}")
    if cartons > max_cartons * 1.02:
        flags.append(f"الكراتين أكثر من الطاقة القصوى للوردية ({_fmt(max_cartons, 1)})")
    if not kwh_meter:
        flags.append("قراءة العداد ناقصة")
    rm_book = ledger_service.bal(conn, "1301", date)["q"]
    if rm_book < rm_kg:
        flags.append(f"رصيد المواد الخام في الدفاتر {_fmt(rm_book)} كغ أقل من المستهلك؛ يُقيَّد بسعر {_fmt(rm_avg)} للكيلو")
    pig_book = ledger_service.bal(conn, "1302", date)["q"]
    if pig_kg and pig_book < pig_kg:
        flags.append(f"رصيد الصبغة في الدفاتر {_fmt(pig_book, 2)} كغ أقل من المستهلك {_fmt(pig_kg, 3)} كغ؛ يُقيَّد بالسعر المعياري")
    ct_book = ledger_service.bal(conn, "1303", date)["q"]
    if ct_book < cartons:
        flags.append(f"رصيد الكراتين الفارغة في الدفاتر {_fmt(ct_book)} أقل من المستخدم")

    return {
        "dep": dep, "downMin": down_min, "downReason": sh["down_reason"] or "", "eff": r2(eff), "perf": r2(perf),
        "lostDown": r2(lost_down), "lostOther": r2(lost_other), "kwhMeter": kwh_meter, "kwhChiller": kwh_chiller,
        "kwh": kwh, "elec": elec, "rmKg": rm_kg, "rmAvg": r2(rm_avg), "rmCost": rm_cost, "pigKg": pig_kg,
        "pigAvg": r2(pig_avg), "pigCost": pig_cost, "cartons": cartons, "ctAvg": r2(ct_avg), "ctCost": ct_cost,
        "labor": labor, "total": total, "per": r2(per), "perSar": r2(per / s["fx"]),
        "marginSar": r2(s["priceSar"] - per / s["fx"]), "matPerCarton": r2(mat_per_carton),
        "expCartons": exp_cartons, "maxCartons": r2(max_cartons), "kwhPrice": s["kwhPrice"], "flags": flags,
    }


# ---------------------------------------------------------------- approve / reject (§7.3)

def approve(conn: sqlite3.Connection, shift_id: int, user: User) -> dict[str, Any]:
    access.require_owner(user)
    with transaction(conn):
        sh = shifts_repo.get(conn, shift_id)
        if not sh:
            raise NotFound("الوردية غير موجودة")
        if sh["status"] != "pending":
            raise Conflict("الوردية ليست بانتظار الاعتماد")
        c = shift_cost(conn, sh)
        if not c["cartons"]:
            raise DomainError("لا يمكن اعتماد وردية بلا إنتاج")
        lines = [
            {"a": "1305", "d": c["total"], "qty": c["cartons"], "cc": "prod"},
            {"a": "1301", "c": c["rmCost"], "qty": c["rmKg"]},
            {"a": "1302", "c": c["pigCost"], "qty": c["pigKg"]},
            {"a": "1303", "c": c["ctCost"], "qty": c["cartons"]},
            {"a": "1401", "c": c["elec"], "party": ELECTRICITY_STATION},
        ]
        if c["labor"]:
            lines.append({"a": "5201", "c": c["labor"], "shift": sh["shift"], "memo": "تحميل أجور وإعاشة الوردية على الإنتاج"})
        if c["dep"]:
            lines.append({"a": "5205", "c": c["dep"], "cc": "prod", "memo": "تحميل إهلاك الآلات والقالب على إنتاج الوردية"})
        breakdown = {k: v for k, v in c.items() if k != "flags"}
        memo = (f"إنتاج الوردية {sh['shift']} {sh['date']}: {_fmt(c['cartons'])} كرتون "
                f"({_fmt(c['rmKg'])} كغ مواد، {_fmt(c['kwh'])} ك.و)")
        res = ledger_service.post(conn, {
            "date": sh["date"], "memo": memo, "src": "shift", "ref": f"{sh['date']}-{sh['shift']}", "lines": lines,
            "meta": {"shiftId": sh["id"], "date": sh["date"], "shift": sh["shift"], "cost": breakdown},
        }, user)
        shifts_repo.set_status(conn, sh["id"], "approved", res["id"], breakdown, user["id"], now_iso())
    return res


def reject(conn: sqlite3.Connection, shift_id: int, user: User) -> None:
    access.require_owner(user)
    with transaction(conn):
        sh = shifts_repo.get(conn, shift_id)
        if not sh:
            raise NotFound("الوردية غير موجودة")
        if sh["status"] != "pending":
            raise Conflict("الوردية ليست بانتظار الاعتماد")
        shifts_repo.set_status(conn, sh["id"], "rejected", None, None, user["id"], now_iso())


def absorb_late_labor(conn: sqlite3.Connection, entries: list[dict[str, Any]], user: User) -> list[dict[str, Any]]:
    """Wages recorded for a shift that is already approved still belong to its product cost.

    The prototype silently left them as an expense; here they are moved into finished
    goods with a small follow-up entry.
    """
    totals: dict[tuple[str, str], float] = {}
    for e in entries:
        for line in e["lines"]:
            if line["a"] == "5201" and line.get("shift") in SHIFTS:
                key = (e["date"], line["shift"])
                totals[key] = totals.get(key, 0) + (line.get("d") or 0) - (line.get("c") or 0)
    posted = []
    for (date, shift), amount in totals.items():
        amount = r2(amount)
        approved = shifts_repo.approved_for(conn, date, shift)
        if amount <= 0 or not approved:
            continue
        # Keep the shift's stored cost in step, so reports and analytics include these wages.
        cost = with_labor_delta(approved["cost"], approved["cartons"], amount, settings_service.get(conn))
        shifts_repo.update_cost(conn, approved["id"], cost)
        posted.append(ledger_service.post(conn, {
            "date": date, "memo": f"تحميل أجور لاحقة على إنتاج الوردية {shift} {date}", "src": "shift",
            "ref": f"{date}-{shift}-late", "lines": [
                {"a": "1305", "d": amount, "cc": "prod"},
                {"a": "5201", "c": amount, "shift": shift, "memo": "أجور سُجلت بعد اعتماد الوردية"},
            ], "meta": {"lateLabor": True, "date": date, "shift": shift},
        }, user))
    return posted


# ---------------------------------------------------------------- listing

def public(sh: dict[str, Any], with_cost: bool) -> dict[str, Any]:
    out = {
        "id": sh["id"], "date": sh["date"], "shift": sh["shift"], "byName": sh["by_name"], "meterStart": sh["meter_start"],
        "meterEnd": sh["meter_end"], "bags": sh["bags"], "extraKg": sh["extra_kg"], "cartons": sh["cartons"],
        "scrapKg": sh["scrap_kg"], "shotsStart": sh["shots_start"], "shotsEnd": sh["shots_end"], "downMin": sh["down_min"],
        "downReason": sh["down_reason"], "notes": sh["notes"], "status": sh["status"], "createdAt": sh["created_at"],
    }
    if with_cost:
        out["cost"] = sh.get("cost")
    return out


def list_for(conn: sqlite3.Connection, user: User) -> list[dict[str, Any]]:
    """Owner: every shift, with the live cost and flags on pending ones.
    Supervisor: only their own shifts and no money figures (§14)."""
    if access.is_owner(user):
        rows = shifts_repo.list_all(conn, limit=200)
        out = []
        for sh in rows:
            item = public(sh, with_cost=True)
            if sh["status"] == "pending":
                item["cost"] = shift_cost(conn, sh)
            out.append(item)
        out.sort(key=lambda x: 0 if x["status"] == "pending" else 1)
        return out
    if user["role"] == "supervisor":
        return [public(sh, with_cost=False) for sh in shifts_repo.list_all(conn, created_by=user["id"], limit=20)]
    raise Forbidden("ليست لديك صلاحية عرض الورديات")
