"""Fixed business vocabulary: chart of accounts, form categories, defaults (spec §2–§5)."""

# code: (Arabic name, type, currency or None, quantity unit or None)
# Types: A asset, L liability, E equity, R revenue, X expense.
ACCOUNTS: dict[str, tuple[str, str, str | None, str | None]] = {
    "1101": ("الصندوق (نقد)", "A", None, None),
    "1102": ("حساب المصنع – ريال سعودي", "A", "SAR", None),
    "1103": ("حساب المصنع – ريال يمني", "A", None, None),
    "1104": ("العُهد", "A", None, None),
    "1106": ("سلف الموظفين", "A", None, None),
    "1107": ("محفظة جيب", "A", None, None),
    "1108": ("محفظة إيزي", "A", None, None),
    "1109": ("محفظة فلوسك", "A", None, None),
    "1201": ("العملاء", "A", None, None),
    "1203": ("مخصص الديون المشكوك فيها", "A", None, None),
    "1301": ("مواد خام HDPE", "A", None, "كغ"),
    "1302": ("صبغة (ماستر باتش)", "A", None, "كغ"),
    "1303": ("كراتين وأكياس فارغة", "A", None, "كرتون"),
    "1305": ("غطايا تامة", "A", None, "كرتون"),
    "1401": ("حساب محطة العهد – كهرباء مدفوعة مقدماً", "A", None, None),
    "1402": ("ضريبة القيمة المضافة – مدخلات", "A", None, None),
    "1501": ("أصول ومعدات", "A", None, None),
    "1502": ("مجمع إهلاك الأصول", "A", None, None),
    "2101": ("الموردون", "L", None, None),
    "2102": ("قروض وسلف", "L", None, None),
    "2301": ("ضريبة القيمة المضافة – مخرجات", "L", None, None),
    "2302": ("ضرائب أخرى مستحقة", "L", None, None),
    "2303": ("زكاة مستحقة", "L", None, None),
    "3101": ("رأس المال وجاري المالك", "E", None, None),
    "4101": ("المبيعات", "R", None, None),
    "4201": ("إيرادات أخرى", "R", None, None),
    "5101": ("تكلفة المبيعات", "X", None, None),
    "5102": ("فروق جرد ومواد التشغيل التجريبي", "X", None, None),
    "5201": ("أجور وإعاشة الإنتاج", "X", None, None),
    "5202": ("كهرباء غير محمّلة", "X", None, None),
    "5203": ("مستلزمات وأدوات وصيانة", "X", None, None),
    "5204": ("صبغة ومواد مساعدة", "X", None, None),
    "5205": ("إهلاك الآلات والقوالب", "X", None, None),
    "6101": ("مصاريف إدارية وعامة", "X", None, None),
    "6102": ("رسوم وعمولات الحوالات", "X", None, None),
    "6103": ("فروق صرف عملة", "X", None, None),
    "6104": ("ضرائب ورسوم", "X", None, None),
    "6105": ("الزكاة", "X", None, None),
    "6106": ("ديون مشكوك فيها", "X", None, None),
}

STOCK_ACCOUNTS = ("1301", "1302", "1303", "1305")
MONEY_ACCOUNTS = ("1101", "1102", "1103", "1104", "1107", "1108", "1109")


def acc_name(code: str) -> str:
    return ACCOUNTS[code][0] if code in ACCOUNTS else code


def acc_unit(code: str) -> str:
    return (ACCOUNTS.get(code) or ("", "", None, None))[3] or ""


SOURCES = {
    "sale": "مبيعات",
    "in": "حوالة واردة",
    "out": "حوالة صادرة",
    "exp": "مصروفات",
    "shift": "وردية إنتاج",
    "fx": "صرف عملة",
    "xfer": "تحويل داخلي",
    "adj": "مطابقة رصيد",
    "count": "جرد",
    "manual": "قيد يدوي",
    "rev": "قيد عكسي",
}

PARTY_TYPES = {
    "customer": "عميل",
    "supplier": "مورد",
    "custodian": "صاحب عهدة",
    "lender": "مُقرض",
    "owner": "المالك",
    "other": "أخرى",
}

ROLES = {
    "owner": "المالك",
    "entry": "مدخل بيانات",
    "reviewer": "مراجع أو شريك",
    "supervisor": "مشرف وردية",
    "none": "بلا صلاحية",
}

# §5.4 expense categories: key -> (label, account)
EXP_CATS: dict[str, tuple[str, str]] = {
    "wages": ("أجور عمال", "5201"),
    "tech": ("أجور مهندسين وفنيين", "5201"),
    "meals": ("إعاشة (وجبات وماء)", "5201"),
    "tools": ("مستلزمات وأدوات وصيانة", "5203"),
    "pigment": ("صبغة ومواد مساعدة", "5204"),
    "admin": ("مصاريف إدارية وعامة", "6101"),
    "advrep": ("خصم سلفة", "1106"),
}

# §5.3 outgoing transfer purposes: key -> (label, debit account)
OUT_PURPOSES: dict[str, tuple[str, str]] = {
    "rm": ("شراء مواد خام HDPE", "1301"),
    "cartons": ("شراء كراتين وأكياس", "1303"),
    "pigment": ("شراء صبغة", "1302"),
    "custody": ("عهدة لموظف", "1104"),
    "power": ("دفعة لمحطة العهد (كهرباء)", "1401"),
    "supplier": ("سداد مورد", "2101"),
    "tools": ("مستلزمات وأدوات وصيانة", "5203"),
    "admin": ("مصروف إداري", "6101"),
    "asset": ("أصل أو معدات", "1501"),
    "loan": ("سداد قرض أو سلفة", "2102"),
    "owner": ("مسحوبات المالك", "3101"),
    "advance": ("سلفة لموظف", "1106"),
    "zakat": ("سداد الزكاة", "2303"),
    "tax": ("سداد ضريبة", "2301"),
}
QTY_PURPOSES = ("rm", "cartons", "pigment")
PARTY_PURPOSES = ("custody", "supplier", "loan", "advance")

# "Via" (عبر): key -> (label, account or None for the exchanger, which depends on currency)
VIA: dict[str, tuple[str, str | None]] = {
    "exch": ("حساب المصنع لدى الصرّاف", None),
    "jeeb": ("محفظة جيب", "1107"),
    "easy": ("محفظة إيزي", "1108"),
    "floosak": ("محفظة فلوسك", "1109"),
    "cash": ("الصندوق", "1101"),
}

SHIFTS = ("صباحية", "مسائية")
EXP_SHIFTS = ("صباحية", "مسائية", "عام")

DOWN_REASONS = (
    "عطل ماكينة",
    "عطل قالب أو فتحة",
    "انتظار مواد",
    "انقطاع كهرباء",
    "تغيير لون أو قالب",
    "صيانة دورية",
    "نقص عمال",
    "أخرى",
)

ELECTRICITY_STATION = "محطة العهد"

# §2 factory facts, editable in Settings.
DEFAULT_SETTINGS: dict = {
    "fx": 140,
    "usdSar": 3.75,
    "rmPriceSarTon": 7500,
    "bagKg": 25,
    "pigmentGPerBag": 30,
    "pigmentPriceSar": 350,
    "pigmentCoverKg": 1500,
    "cartonCost": 550,
    "cartonNetKg": 9.675,
    "capsPerCarton": 5500,
    "capWeightG": 1.9,
    "cavities": 48,
    "cycleSec": 13,
    "shiftHours": 12,
    "kwhPrice": 180,
    "chillerKw": 26.14,
    "chillerLoad": 0.5,
    "priceSar": 155,
    "normalScrapPct": 5,
    "plannedCartonsDay": 50,
    "collectionDays": 7,
    "minStockDays": 3,
    "costingStart": "2026-10-14",
    "lockDate": "",
    "dualControl": True,
    "vatEnabled": False,
    "vatRate": 0,
    "vatNo": "",
    "zakatRate": 2.5,
    "nisabYer": 0,
    "creditLimits": {},
    "provPct": [0, 0, 10, 25, 50],
}

# Numeric settings the owner edits on the settings screen.
NUMERIC_SETTINGS = (
    "fx", "usdSar", "rmPriceSarTon", "bagKg", "pigmentGPerBag", "pigmentPriceSar", "pigmentCoverKg",
    "cartonCost", "cartonNetKg", "capsPerCarton", "capWeightG", "cavities", "cycleSec", "shiftHours",
    "kwhPrice", "chillerKw", "chillerLoad", "priceSar", "normalScrapPct", "plannedCartonsDay",
    "collectionDays", "minStockDays", "vatRate", "zakatRate", "nisabYer",
)
# Settings that must stay strictly positive because formulas divide by them.
POSITIVE_SETTINGS = (
    "fx", "usdSar", "bagKg", "pigmentGPerBag", "pigmentCoverKg", "cartonNetKg", "capsPerCarton",
    "cavities", "cycleSec", "shiftHours",
)

DEFAULT_COST_CENTERS = [
    ("prod", "الإنتاج – ماكينة هايتيان 3200"),
    ("admin", "الإدارة"),
    ("sales", "المبيعات والتوزيع"),
]

DEFAULT_PARTIES = [
    ("سنوان بلاست", "customer"),
    ("محمد يحيى", "customer"),
    ("أسامة السواري", "supplier"),
    (ELECTRICITY_STATION, "supplier"),
    ("علي أبو طالب", "lender"),
]


def default_cc(account: str) -> str:
    """§9: 6xxx → admin; sales and COGS → sales; everything else → prod."""
    if account.startswith("6"):
        return "admin"
    if account in ("4101", "5101"):
        return "sales"
    return "prod"
