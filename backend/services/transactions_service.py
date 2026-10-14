"""Transaction forms (spec §5): each form becomes one or more journal entries.

``build`` turns a form into entries without saving (the preview). ``save`` builds the
same entries again and either posts them or, under dual control (§6), files them as a
payment request.
"""

import sqlite3
from typing import Any, Callable

from database import transaction
from repositories import entries_repo, shifts_repo
from services import access, auth_service, ledger_service, requests_service, settings_service, shifts_service
from services.chart import (
    ACCOUNTS, ELECTRICITY_STATION, EXP_CATS, EXP_SHIFTS, OUT_PURPOSES, PARTY_PURPOSES, QTY_PURPOSES, VIA,
)
from services.costing import pig_kg_cost, rm_kg_cost
from utils.dates import is_iso
from utils.errors import DomainError, need
from utils.money import is_num, r2

Form = dict[str, Any]
User = dict[str, Any]

DUAL_CONTROL_KINDS = ("out", "exp", "fx")


def _fmt(x: float, d: int = 0) -> str:
    return f"{x:,.{d}f}"


def _num(form: Form, key: str) -> float | None:
    v = form.get(key)
    return float(v) if is_num(v) else None


def _text(form: Form, key: str) -> str:
    return str(form.get(key) or "").strip()


def via_acc(via: str, cur: str) -> str:
    acc = VIA.get(via, VIA["exch"])[1]
    return acc or ("1102" if cur == "SAR" else "1103")


def via_line(via: str, cur: str, side: str, yer: float, fc: float | None = None) -> dict[str, Any]:
    line: dict[str, Any] = {"a": via_acc(via, cur), side: yer}
    if line["a"] == "1102" or cur == "SAR":
        line["cur"], line["fc"] = "SAR", fc if fc is not None else 0
    return line


def _date(form: Form) -> str:
    date = _text(form, "date")
    need(is_iso(date), "اختر التاريخ", "date")
    return date


def _cur(form: Form) -> str:
    cur = _text(form, "cur") or "YER"
    need(cur in ("SAR", "YER"), "العملة غير صحيحة", "cur")
    return cur


def _via(form: Form) -> str:
    via = _text(form, "via") or "exch"
    need(via in VIA, "اختر الحساب", "via")
    return via


def _known_party(conn: sqlite3.Connection, name: str, type_: str | None, field: str, message: str) -> None:
    names = settings_service.party_names(conn, type_)
    need(name in names, message, field)


# ---------------------------------------------------------------- 5.1 sale

def build_sale(conn: sqlite3.Connection, form: Form, user: User) -> list[dict[str, Any]]:
    s = settings_service.get(conn)
    date, ref, party = _date(form), _text(form, "ref"), _text(form, "party")
    qty, price, rate = _num(form, "qty"), _num(form, "price"), _num(form, "rate")
    need(party, "اكتب اسم العميل", "party")
    _known_party(conn, party, "customer", "party", "العميل غير موجود في قائمة الأطراف. أضفه من الإعدادات أولاً.")
    need(qty and qty > 0, "اكتب عدد الكراتين", "qty")
    need(price and price > 0, "اكتب سعر الكرتون", "price")
    need(rate and rate > 0, "اكتب سعر الصرف", "rate")
    if ref:
        dup = entries_repo.find_ref(conn, "sale", ref)
        need(not dup, f"الفاتورة {ref} مسجلة مسبقاً", "ref")
    sar = r2(qty * price)
    yer = r2(sar * rate)
    limit = float((s.get("creditLimits") or {}).get(party) or 0)
    if limit:
        after = r2(ledger_service.pbal(conn, "1201", party)["fc"] + sar)
        override = bool(form.get("overLimit")) and access.is_owner(user)
        if after > limit and not override:
            if access.is_owner(user):
                raise DomainError(f"رصيد {party} سيصبح {_fmt(after)} ر.س، فوق سقف الائتمان {_fmt(limit)} ر.س. "
                                  "حصّل أولاً أو أشّر على الموافقة.", "overLimit")
            raise DomainError(f"هذه الفاتورة تتجاوز سقف ائتمان {party}. اطلب موافقة المالك.", "party")
    vat_rate = (float(s.get("vatRate") or 0) / 100) if s.get("vatEnabled") else 0
    vat_s = r2(sar * vat_rate)
    vat_y = r2(vat_s * rate)
    lines = [{"a": "1201", "d": r2(yer + vat_y), "party": party, "cur": "SAR", "fc": r2(sar + vat_s)}, {"a": "4101", "c": yer}]
    if vat_y:
        lines.append({"a": "2301", "c": vat_y, "cur": "SAR", "fc": vat_s})
    memo = f"فاتورة مبيعات {ref}: {_fmt(qty, 0 if qty == int(qty) else 2)} كرتون × {_fmt(price, 2 if price % 1 else 0)} ر.س – {party}"
    if vat_y:
        memo += f" + ضريبة {s['vatRate']}%"
    out = [{"date": date, "memo": memo, "src": "sale", "ref": ref, "party": party, "lines": lines,
            "meta": {"cartons": qty, "price": price, "rate": rate, "vat": vat_s}}]
    if date >= s["costingStart"]:
        fg = ledger_service.bal(conn, "1305", date)
        unit = fg["y"] / fg["q"] if fg["q"] > 0 and fg["y"] > 0 else None
        if unit is None:
            last = shifts_repo.last_approved(conn, date)
            unit = (last or {}).get("cost", {}).get("per") if last else None
        if unit:
            cogs = r2(qty * unit)
            note = " (المخزون في الدفاتر أقل من الكمية)" if fg["q"] < qty else ""
            out.append({"date": date, "memo": f"تكلفة مبيعات الفاتورة {ref}: {_fmt(qty)} كرتون × {_fmt(unit, 1)}{note}",
                        "src": "sale", "ref": ref, "party": party, "is_cogs": True,
                        "lines": [{"a": "5101", "d": cogs}, {"a": "1305", "c": cogs, "qty": qty}], "meta": {"cogs": True}})
        else:
            out[0]["memo"] += " – بدون تكلفة مبيعات (لا مخزون مقيَّم بعد)"
    return out


# ---------------------------------------------------------------- 5.2 incoming

def build_in(conn: sqlite3.Connection, form: Form, user: User) -> list[dict[str, Any]]:
    date, ref, sender, party = _date(form), _text(form, "ref"), _text(form, "sender"), _text(form, "party")
    amount, rate, cur, via = _num(form, "amount"), _num(form, "rate"), _cur(form), _via(form)
    purpose = _text(form, "purpose") or "customer"
    need(purpose in ("customer", "owner", "loan", "other"), "اختر الغرض", "purpose")
    need(amount and amount > 0, "اكتب المبلغ", "amount")
    need(rate and rate > 0, "اكتب سعر الصرف", "rate")
    if ref:
        dup = entries_repo.find_ref(conn, "in", ref)
        need(not dup, f"الحوالة {ref} مسجلة مسبقاً", "ref")
    yer = r2(amount * rate) if cur == "SAR" else amount
    lines = [via_line(via, cur, "d", yer, amount if cur == "SAR" else None)]
    if purpose == "customer":
        need(party, "اختر العميل", "party")
        _known_party(conn, party, "customer", "party", "العميل غير موجود في قائمة الأطراف")
        sar_given = _num(form, "sar")
        sar = amount if cur == "SAR" else (sar_given if sar_given and sar_given > 0 else r2(amount / rate))
        book = r2(sar * rate)
        lines.append({"a": "1201", "c": book, "party": party, "cur": "SAR", "fc": r2(sar)})
        diff = r2(yer - book)
        if abs(diff) > 0.5:
            lines.append({"a": "6103", "c": diff} if diff > 0 else {"a": "6103", "d": -diff})
    elif purpose == "owner":
        lines.append({"a": "3101", "c": yer, "party": settings_service.owner_name(conn)})
    elif purpose == "loan":
        need(party, "اكتب اسم المُقرض", "party")
        _known_party(conn, party, None, "party", "الطرف غير موجود في قائمة الأطراف")
        lines.append({"a": "2102", "c": yer, "party": party})
    else:
        lines.append({"a": "4201", "c": yer, "party": party or None})
    purpose_label = {"customer": f"سداد {party}", "owner": f"تمويل من المالك {settings_service.owner_name(conn)}",
                     "loan": f"قرض من {party}", "other": "إيراد آخر"}[purpose]
    memo = f"حوالة واردة: {purpose_label}" + (f" – المرسل {sender}" if sender and sender != party else "")
    if via != "exch":
        memo += f" عبر {VIA[via][0]}"
    return [{"date": date, "memo": memo, "src": "in", "ref": ref, "party": party or sender, "lines": lines,
             "meta": {"cur": cur, "amount": amount, "rate": rate, "sender": sender, "via": via, "purpose": purpose}}]


# ---------------------------------------------------------------- 5.3 outgoing

def build_out(conn: sqlite3.Connection, form: Form, user: User) -> list[dict[str, Any]]:
    s = settings_service.get(conn)
    date, ref, ben, party = _date(form), _text(form, "ref"), _text(form, "beneficiary"), _text(form, "party")
    purpose = _text(form, "purpose")
    amount, rate, cur, via = _num(form, "amount"), _num(form, "rate"), _cur(form), _via(form)
    fee, qty, vat = _num(form, "fee") or 0, _num(form, "qty") or 0, (_num(form, "vat") or 0) if s.get("vatEnabled") else 0
    cc = _text(form, "cc") or "prod"
    need(purpose in OUT_PURPOSES, "اختر الغرض", "purpose")
    need(amount and amount > 0, "اكتب المبلغ", "amount")
    need(rate and rate > 0, "اكتب سعر الصرف", "rate")
    need(fee >= 0, "الرسوم غير صحيحة", "fee")
    need(cc in settings_service.cc_ids(conn), "مركز التكلفة غير معروف", "cc")
    if ref:
        dup = entries_repo.find_ref(conn, "out", ref)
        need(not dup, f"الحوالة {ref} مسجلة مسبقاً", "ref")
    label, acc = OUT_PURPOSES[purpose]
    if purpose in QTY_PURPOSES:
        need(qty > 0, "اكتب عدد الكراتين" if purpose == "cartons" else "اكتب الكمية بالكيلو", "qty")
    if purpose in PARTY_PURPOSES:
        need(party, "اكتب اسم الطرف", "party")
        if purpose != "advance":
            _known_party(conn, party, None, "party", "الطرف غير موجود في قائمة الأطراف")
    yer = r2(amount * rate) if cur == "SAR" else amount
    vat_y = r2(vat * rate if cur == "SAR" else vat)
    need(0 <= vat_y < yer, "الضريبة يجب أن تكون أقل من المبلغ", "vat")
    dr: dict[str, Any] = {"a": acc, "d": r2(yer - vat_y)}
    if acc[0] in "56":
        dr["cc"] = cc
    if purpose in QTY_PURPOSES:
        dr["qty"] = qty
    if purpose == "power":
        dr["party"] = ELECTRICITY_STATION
    elif purpose == "owner":
        dr["party"] = settings_service.owner_name(conn)
    elif party:
        dr["party"] = party
    lines = [dr]
    if vat_y:
        lines.append({"a": "1402", "d": vat_y})
    lines.append(via_line(via, cur, "c", yer, amount if cur == "SAR" else None))
    if fee:
        lines += [{"a": "6102", "d": fee}, via_line(via, "YER", "c", fee)]
    who = ben or party
    memo = f"حوالة صادرة: {label}" + (f" – {who}" if who else "")
    if purpose in QTY_PURPOSES:
        memo += f" ({_fmt(qty, 2 if qty % 1 else 0)} {'كرتون' if purpose == 'cartons' else 'كغ'})"
    if via != "exch":
        memo += f" عبر {VIA[via][0]}"
    return [{"date": date, "memo": memo, "src": "out", "ref": ref, "party": party or ben, "lines": lines,
             "meta": {"cur": cur, "amount": amount, "rate": rate, "fee": fee, "purpose": purpose, "via": via}}]


# ---------------------------------------------------------------- 5.4 expenses

def build_exp(conn: sqlite3.Connection, form: Form, user: User) -> list[dict[str, Any]]:
    date = _date(form)
    paid_from = _text(form, "paidFrom") or "3101"
    need(paid_from in ("3101", "1104", "1101"), "اختر مصدر الدفع", "paidFrom")
    if paid_from == "1104":
        party = _text(form, "party")
        need(party, "اكتب صاحب العهدة", "party")
        _known_party(conn, party, "custodian", "party", "صاحب العهدة غير موجود في قائمة الأطراف")
    elif paid_from == "3101":
        party = settings_service.owner_name(conn)
    else:
        party = ""
    ccs = settings_service.cc_ids(conn)
    rows = []
    for i, raw in enumerate(form.get("lines") or []):
        amount = raw.get("amount")
        if not is_num(amount) or amount <= 0:
            continue
        cat = raw.get("cat")
        need(cat in EXP_CATS, f"اختر الفئة في السطر {i + 1}", f"lines.{i}.cat")
        shift = raw.get("shift") or "عام"
        need(shift in EXP_SHIFTS, f"الوردية غير صحيحة في السطر {i + 1}", f"lines.{i}.shift")
        cc = raw.get("cc") or ("admin" if cat == "admin" else "prod")
        need(cc in ccs, f"مركز التكلفة غير معروف في السطر {i + 1}", f"lines.{i}.cc")
        rows.append({"desc": str(raw.get("desc") or "").strip(), "cat": cat, "shift": shift, "cc": cc, "amount": float(amount), "i": i})
    need(rows, "أضف سطراً واحداً على الأقل بمبلغ", "lines")
    deductions = [r for r in rows if r["cat"] == "advrep"]
    expenses = [r for r in rows if r["cat"] != "advrep"]
    for r in deductions:
        need(r["desc"], "اكتب اسم الموظف في بيان سطر خصم السلفة", f"lines.{r['i']}.desc")
    total = r2(sum(r["amount"] for r in expenses) - sum(r["amount"] for r in deductions))
    need(total >= 0, "الخصومات أكبر من المصروفات", "lines")
    lines: list[dict[str, Any]] = []
    for r in expenses:
        label, acc = EXP_CATS[r["cat"]]
        line = {"a": acc, "d": r["amount"], "shift": r["shift"], "cc": r["cc"], "memo": f"{r['desc'] or label} – {label}"}
        lines.append(line)
    for r in deductions:
        lines.append({"a": "1106", "c": r["amount"], "party": r["desc"], "memo": f"خصم من سلفة {r['desc']}"})
    lines.append({"a": paid_from, "c": total, "party": party or None})
    who = {"1104": f" من عهدة {party}", "3101": f" دفعها المالك {party}", "1101": " من الصندوق"}[paid_from]
    return [{"date": date, "memo": f"مصروفات يوم {date}{who}", "src": "exp", "party": party, "lines": lines,
             "meta": {"paidFrom": paid_from}}]


# ---------------------------------------------------------------- 5.5 currency exchange

def build_fx(conn: sqlite3.Connection, form: Form, user: User) -> list[dict[str, Any]]:
    date, ref = _date(form), _text(form, "ref")
    amount, rate = _num(form, "amount"), _num(form, "rate")
    need(amount and amount > 0, "اكتب مبلغ الريال السعودي", "amount")
    need(rate and rate > 0, "اكتب سعر الصرف", "rate")
    b = ledger_service.bal(conn, "1102")
    need(b["fc"] >= amount, f"رصيد السعودي في الدفاتر {_fmt(b['fc'], 2)} أقل من المبلغ", "amount")
    book = r2(amount * (b["y"] / b["fc"]))
    got = r2(amount * rate)
    diff = r2(got - book)
    lines = [{"a": "1103", "d": got}, {"a": "1102", "c": book, "cur": "SAR", "fc": amount}]
    if abs(diff) > 0.5:
        lines.append({"a": "6103", "c": diff} if diff > 0 else {"a": "6103", "d": -diff})
    return [{"date": date, "memo": f"صرف {_fmt(amount, 2 if amount % 1 else 0)} ر.س بسعر {rate:g}", "src": "fx", "ref": ref,
             "lines": lines, "meta": {"amount": amount, "rate": rate}}]


# ---------------------------------------------------------------- 5.6 internal transfer

def build_xfer(conn: sqlite3.Connection, form: Form, user: User) -> list[dict[str, Any]]:
    s = settings_service.get(conn)
    date, ref = _date(form), _text(form, "ref")
    src_via, dst_via = _text(form, "fromVia") or "exch", _text(form, "toVia") or "jeeb"
    need(src_via in VIA and dst_via in VIA, "اختر الحسابين", "fromVia")
    amount, cur, fee = _num(form, "amount"), _cur(form), _num(form, "fee") or 0
    need(amount and amount > 0, "اكتب المبلغ", "amount")
    need(fee >= 0, "الرسوم غير صحيحة", "fee")
    need(via_acc(src_via, cur) != via_acc(dst_via, cur), "اختر حسابين مختلفين", "toVia")
    yer = r2(amount * s["fx"]) if cur == "SAR" else amount
    fc = amount if cur == "SAR" else None
    lines = [via_line(dst_via, cur, "d", yer, fc), via_line(src_via, cur, "c", yer, fc)]
    if fee:
        lines += [{"a": "6102", "d": fee}, via_line(src_via, "YER", "c", fee)]
    unit = "ر.س" if cur == "SAR" else "ر.ي"
    return [{"date": date, "memo": f"تحويل {_fmt(amount)} {unit} من {VIA[src_via][0]} إلى {VIA[dst_via][0]}", "src": "xfer",
             "ref": ref, "lines": lines, "meta": {"cur": cur, "amount": amount, "fee": fee}}]


# ---------------------------------------------------------------- 5.7 balance adjustment

ADJ_ACCOUNTS = ("1103", "1102", "1101", "1104", "1107", "1108", "1109")
ADJ_COUNTERS = ("3101", "5203", "4201")


def build_adj(conn: sqlite3.Connection, form: Form, user: User) -> list[dict[str, Any]]:
    s = settings_service.get(conn)
    date, acc, counter, party = _date(form), _text(form, "account"), _text(form, "counter") or "3101", _text(form, "party")
    actual = _num(form, "actual")
    need(acc in ADJ_ACCOUNTS, "اختر الحساب", "account")
    need(counter in ADJ_COUNTERS, "اختر الحساب المقابل", "counter")
    need(actual is not None, "اكتب الرصيد الفعلي", "actual")
    if acc == "1104":
        need(party, "اكتب صاحب العهدة", "party")
    pc = settings_service.owner_name(conn) if counter == "3101" else None
    if acc == "1102":
        b = ledger_service.bal(conn, "1102")
        dfc = r2(actual - b["fc"])
        need(abs(dfc) > 0.004, "الرصيد مطابق", "actual")
        y = r2(abs(dfc) * s["fx"])
        lines = ([{"a": "1102", "d": y, "cur": "SAR", "fc": dfc}, {"a": counter, "c": y, "party": pc}] if dfc > 0
                 else [{"a": counter, "d": y, "party": pc}, {"a": "1102", "c": y, "cur": "SAR", "fc": -dfc}])
    else:
        b = ledger_service.pbal(conn, "1104", party) if acc == "1104" else ledger_service.bal(conn, acc)
        dy = r2(actual - b["y"])
        need(abs(dy) > 0.5, "الرصيد مطابق", "actual")
        pa = party if acc == "1104" else None
        lines = ([{"a": acc, "d": dy, "party": pa}, {"a": counter, "c": dy, "party": pc}] if dy > 0
                 else [{"a": counter, "d": -dy, "party": pc}, {"a": acc, "c": -dy, "party": pa}])
    name = ACCOUNTS[acc][0] + (f" {party}" if acc == "1104" else "")
    return [{"date": date, "memo": f"مطابقة رصيد {name} إلى {_fmt(actual, 2 if actual % 1 else 0)}", "src": "adj",
             "party": party if acc == "1104" else "", "lines": lines, "meta": {"actual": actual, "account": acc}}]


# ---------------------------------------------------------------- 5.8 stock count

def build_count(conn: sqlite3.Connection, form: Form, user: User) -> list[dict[str, Any]]:
    s = settings_service.get(conn)
    date = _date(form)
    items = [("1301", "rm", rm_kg_cost(s)), ("1302", "pig", pig_kg_cost(s)), ("1303", "ct", s["cartonCost"]), ("1305", "fg", None)]
    lines: list[dict[str, Any]] = []
    for acc, key, std in items:
        q = _num(form, key)
        if q is None:
            continue
        need(q >= 0, "الكمية لا تكون سالبة", key)
        b = ledger_service.bal(conn, acc)
        dq = round(q - b["q"], 4)
        if abs(dq) < 0.001:
            continue
        unit = b["y"] / b["q"] if b["q"] > 0 and b["y"] > 0 else std
        if acc == "1305" and not unit:
            last = shifts_repo.last_approved(conn)
            unit = (last or {}).get("cost", {}).get("per") if last else None
            unit = unit or (s["cartonNetKg"] * rm_kg_cost(s) + s["cartonCost"])
        y = r2(abs(dq) * unit)
        if dq > 0:
            lines += [{"a": acc, "d": y, "qty": dq}, {"a": "5102", "c": y}]
        else:
            lines += [{"a": "5102", "d": y}, {"a": acc, "c": y, "qty": -dq}]
    need(lines, "لا فروق بين الجرد والدفاتر")
    return [{"date": date, "memo": "جرد مخزون فعلي وتسوية الفروق", "src": "count", "lines": lines, "meta": {}}]


# ---------------------------------------------------------------- 5.9 manual entry

def build_manual(conn: sqlite3.Connection, form: Form, user: User) -> list[dict[str, Any]]:
    s = settings_service.get(conn)
    date, memo, ref = _date(form), _text(form, "memo"), _text(form, "ref")
    need(memo, "اكتب البيان", "memo")
    lines = []
    for i, raw in enumerate(form.get("lines") or []):
        d, c = raw.get("d") or 0, raw.get("c") or 0
        need(is_num(d) and is_num(c) and d >= 0 and c >= 0, f"مبلغ غير صحيح في السطر {i + 1}", f"lines.{i}")
        if not d and not c:
            continue
        acc = raw.get("a")
        need(acc in ACCOUNTS, f"اختر الحساب في السطر {i + 1}", f"lines.{i}.a")
        line: dict[str, Any] = {"a": acc, "d": d, "c": c}
        if str(raw.get("party") or "").strip():
            line["party"] = str(raw["party"]).strip()
        if acc == "1102":
            line["cur"], line["fc"] = "SAR", r2((d or c) / s["fx"])
        lines.append(line)
    need(len(lines) >= 2, "القيد يحتاج سطرين على الأقل", "lines")
    return [{"date": date, "memo": memo, "src": "manual", "ref": ref, "lines": lines, "meta": {}}]


BUILDERS: dict[str, Callable[[sqlite3.Connection, Form, User], list[dict[str, Any]]]] = {
    "sale": build_sale, "in": build_in, "out": build_out, "exp": build_exp, "fx": build_fx,
    "xfer": build_xfer, "adj": build_adj, "count": build_count, "manual": build_manual,
}


def build(conn: sqlite3.Connection, kind: str, form: Form, user: User) -> list[dict[str, Any]]:
    access.require_form(user, kind)
    if kind not in BUILDERS:
        raise DomainError("نوع غير معروف")
    entries = BUILDERS[kind](conn, form, user)
    # Run the posting rules now so the preview shows the same errors the save would.
    return [ledger_service.validate(conn, e) for e in entries]


def needs_approval(conn: sqlite3.Connection, kind: str, user: User) -> bool:
    s = settings_service.get(conn)
    return bool(s.get("dualControl")) and kind in DUAL_CONTROL_KINDS and auth_service.has_other_approver(conn, user["id"])


def save(conn: sqlite3.Connection, kind: str, form: Form, user: User) -> dict[str, Any]:
    """Post the form, or file it as a payment request under dual control."""
    entries = build(conn, kind, form, user)
    if needs_approval(conn, kind, user):
        req = requests_service.create(conn, kind, entries, user)
        return {"request": req, "posted": []}
    with transaction(conn):
        posted = ledger_service.post_many(conn, entries, user)
        if kind == "exp":
            posted += shifts_service.absorb_late_labor(conn, entries, user)
    return {"request": None, "posted": posted}


def preview(conn: sqlite3.Connection, kind: str, form: Form, user: User) -> dict[str, Any]:
    entries = build(conn, kind, form, user)
    return {"entries": entries, "needsApproval": needs_approval(conn, kind, user)}

