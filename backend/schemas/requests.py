"""Request bodies. Shapes and types are checked here; business rules live in the services."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Money = float
Shift = Literal["صباحية", "مسائية"]


class Body(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ---- auth and users ----

class LoginRequest(Body):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


class PasswordChange(Body):
    current: str = Field(max_length=200)
    new: str = Field(max_length=200)


class UserCreate(Body):
    username: str = Field(max_length=40)
    label: str = Field(default="", max_length=80)
    password: str = Field(max_length=200)
    role: Literal["entry", "reviewer", "supervisor", "none"]
    approver: bool = False


class UserUpdate(Body):
    label: str | None = Field(default=None, max_length=80)
    role: Literal["entry", "reviewer", "supervisor", "none"] | None = None
    approver: bool | None = None
    active: bool | None = None
    password: str | None = Field(default=None, max_length=200)


# ---- settings ----

class PartyCreate(Body):
    name: str = Field(max_length=80)
    type: Literal["customer", "supplier", "custodian", "lender", "owner", "other"]


class CostCenterCreate(Body):
    name: str = Field(max_length=80)


class CreditLimits(Body):
    limits: dict[str, float]


# ---- transaction forms (§5) ----

class SaleForm(Body):
    date: str
    ref: str = Field(default="", max_length=40)
    party: str = Field(default="", max_length=80)
    qty: float | None = None
    price: float | None = None
    rate: float | None = None
    overLimit: bool = False


class InForm(Body):
    date: str
    ref: str = Field(default="", max_length=40)
    sender: str = Field(default="", max_length=80)
    amount: float | None = None
    cur: Literal["SAR", "YER"] = "SAR"
    rate: float | None = None
    via: str = "exch"
    purpose: Literal["customer", "owner", "loan", "other"] = "customer"
    party: str = Field(default="", max_length=80)
    sar: float | None = None


class OutForm(Body):
    date: str
    ref: str = Field(default="", max_length=40)
    beneficiary: str = Field(default="", max_length=80)
    purpose: str = ""
    amount: float | None = None
    cur: Literal["SAR", "YER"] = "YER"
    rate: float | None = None
    via: str = "exch"
    cc: str = "prod"
    fee: float | None = None
    vat: float | None = None
    qty: float | None = None
    party: str = Field(default="", max_length=80)


class ExpLine(Body):
    desc: str = Field(default="", max_length=120)
    cat: str = "wages"
    shift: Literal["صباحية", "مسائية", "عام"] = "عام"
    cc: str = ""
    amount: float | None = None


class ExpForm(Body):
    date: str
    paidFrom: Literal["3101", "1104", "1101"] = "3101"
    party: str = Field(default="", max_length=80)
    lines: list[ExpLine] = Field(default_factory=list, max_length=60)


class FxForm(Body):
    date: str
    amount: float | None = None
    rate: float | None = None
    ref: str = Field(default="", max_length=40)


class XferForm(Body):
    date: str
    fromVia: str = "exch"
    toVia: str = "jeeb"
    amount: float | None = None
    cur: Literal["SAR", "YER"] = "YER"
    fee: float | None = None
    ref: str = Field(default="", max_length=40)


class AdjForm(Body):
    date: str
    account: str
    actual: float | None = None
    counter: str = "3101"
    party: str = Field(default="", max_length=80)


class CountForm(Body):
    date: str
    rm: float | None = None
    pig: float | None = None
    ct: float | None = None
    fg: float | None = None


class ManualLine(Body):
    a: str = ""
    party: str = Field(default="", max_length=80)
    d: float | None = 0
    c: float | None = 0


class ManualForm(Body):
    date: str
    memo: str = Field(default="", max_length=200)
    ref: str = Field(default="", max_length=40)
    lines: list[ManualLine] = Field(default_factory=list, max_length=60)


FORMS: dict[str, type[Body]] = {
    "sale": SaleForm, "in": InForm, "out": OutForm, "exp": ExpForm, "fx": FxForm,
    "xfer": XferForm, "adj": AdjForm, "count": CountForm, "manual": ManualForm,
}


# ---- shifts, advances, approvals ----

class ShiftForm(Body):
    date: str
    shift: Shift
    byName: str = Field(default="", max_length=80)
    meterStart: float | None = None
    meterEnd: float | None = None
    bags: float | None = None
    extraKg: float | None = None
    cartons: float | None = None
    scrapKg: float | None = None
    shotsStart: float | None = None
    shotsEnd: float | None = None
    downMin: float | None = None
    downReason: str = ""
    notes: str = Field(default="", max_length=300)


class AdvanceForm(Body):
    employee: str = Field(max_length=80)
    amount: float | None = None
    installments: float = 1
    reason: str = Field(default="", max_length=200)
    byName: str = Field(default="", max_length=80)


class AdvanceDecision(Body):
    source: Literal["1104", "1101", "1103"]
    custodian: str = Field(default="", max_length=80)


# ---- assets ----

class AssetCreate(Body):
    name: str = Field(max_length=120)
    date: str
    amount: float = 0
    cur: Literal["USD", "SAR", "YER"] = "YER"
    life: float | None = None
    salvage: float = 0
    fund: Literal["3101", "1103", "1102", "2102"] = "3101"
    cc: str = "prod"
    note: str = Field(default="", max_length=200)


class AssetPrice(Body):
    amount: float | None = None
    cur: Literal["USD", "SAR", "YER"] = "USD"
    life: float | None = None
    fund: Literal["3101", "1103", "1102", "2102"] = "3101"


class AssetLife(Body):
    life: float


class DepreciationRun(Body):
    to: str


# ---- reports and reconciliation ----

class BudgetSave(Body):
    month: str
    values: dict[str, float]


class DateOnly(Body):
    date: str | None = None


class FxClose(Body):
    party: str = Field(max_length=80)


class ReconSave(Body):
    key: str = Field(max_length=120)
    lineIds: list[int] = Field(default_factory=list, max_length=20000)
    date: str | None = None
    statement: float | None = None
