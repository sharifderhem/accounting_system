"""Date helpers. Dates are ISO strings (YYYY-MM-DD), compared as text."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from config import settings


def today() -> str:
    """The factory's calendar day (Aden time), not the server's."""
    return datetime.now(ZoneInfo(settings.timezone)).date().isoformat()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse(d: str) -> date:
    return date.fromisoformat(d)


def add_days(d: str, n: int) -> str:
    return (parse(d) + timedelta(days=n)).isoformat()


def prev_day(d: str) -> str:
    return add_days(d, -1)


def next_day(d: str) -> str:
    return add_days(d, 1)


def days_between(a: str, b: str) -> int:
    """Whole days from a to b (b - a)."""
    return (parse(b) - parse(a)).days


def add_years(d: str, years: float) -> str:
    """Purchase date + useful life. Fractional years add their share of 365 days,
    as the prototype did."""
    base = parse(d)
    whole = int(years // 1)
    try:
        shifted = base.replace(year=base.year + whole)
    except ValueError:  # 29 February into a non-leap year
        shifted = base.replace(year=base.year + whole, day=28)
    return (shifted + timedelta(days=round((years % 1) * 365))).isoformat()


def is_iso(d: object) -> bool:
    if not isinstance(d, str) or len(d) != 10:
        return False
    try:
        parse(d)
    except ValueError:
        return False
    return True
