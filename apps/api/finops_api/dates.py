"""Dates and digits for people to read: Solar Hijri with Persian digits in Persian, ISO dates in English.

Python's standard library has no Solar Hijri calendar, so the conversion is the usual arithmetic one (the 33-year
cycle that ICU and browsers use too). Iran has kept UTC+03:30 all year since 2022, so a moment is shown in that
offset without needing a time zone database.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

TEHRAN = timezone(timedelta(hours=3, minutes=30))
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_DAYS_BEFORE_MONTH = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def fa_digits(text: object) -> str:
    return str(text).translate(_FA_DIGITS)


def fa_number(text: str) -> str:
    """"20,574,439.5" -> "۲۰٬۵۷۴٬۴۳۹٫۵": Persian digits and separators, as the voice guideline and the app write them."""
    return fa_digits(text.replace(",", "٬").replace(".", "٫"))


def to_jalali(d: date) -> tuple[int, int, int]:
    """Gregorian date to Solar Hijri (year, month, day)."""
    gy2 = d.year + 1 if d.month > 2 else d.year
    days = (355666 + 365 * d.year + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + d.day
            + _DAYS_BEFORE_MONTH[d.month - 1])
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def _parse(value: object) -> tuple[date, datetime | None] | None:
    """A calendar day, and the moment if there is one. Strings are ISO; a moment without an offset is UTC."""
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=UTC)
        return moment.date(), moment
    if isinstance(value, date):
        return value, None
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        if len(value) == 10:
            return date.fromisoformat(value), None
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    moment = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return moment.date(), moment


def format_day(value: object, lang: str) -> str:
    """۱۴۰۵/۰۸/۱۷ in Persian (the day in Iran, for a moment), 2026-11-08 in English. Anything else as written."""
    parsed = _parse(value)
    if parsed is None:
        return "—" if value is None else str(value)
    day, moment = parsed
    if lang != "fa":
        return (moment.astimezone(UTC).date() if moment else day).isoformat()
    y, m, d = to_jalali(moment.astimezone(TEHRAN).date() if moment else day)
    return fa_digits(f"{y}/{m:02d}/{d:02d}")
