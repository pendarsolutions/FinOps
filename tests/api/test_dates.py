"""Solar Hijri dates for Persian readers (Pendar's voice guideline: ۱۴۰۵/۰۷/۰۵, never a Gregorian date)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from finops_api.dates import fa_digits, format_day, to_jalali


@pytest.mark.parametrize(("gregorian", "jalali"), [
    (date(2026, 3, 21), (1405, 1, 1)),     # Nowruz 1405
    (date(2026, 3, 20), (1404, 12, 29)),   # last day of 1404, a common year
    (date(2025, 3, 20), (1403, 12, 30)),   # 1403 is a leap year: Esfand has 30 days
    (date(2024, 3, 20), (1403, 1, 1)),
    (date(2026, 11, 8), (1405, 8, 17)),
    (date(2026, 9, 22), (1405, 6, 31)),    # the first six months have 31 days
    (date(2026, 9, 23), (1405, 7, 1)),
    (date(2000, 1, 1), (1378, 10, 11)),
])
def test_known_dates(gregorian, jalali):
    assert to_jalali(gregorian) == jalali


def test_every_day_follows_the_one_before():
    """No gaps or repeats over sixteen years, and every month has the length the calendar gives it."""
    d, prev = date(2020, 1, 1), to_jalali(date(2019, 12, 31))
    while d < date(2036, 1, 1):
        y, m, day = cur = to_jalali(d)
        py, pm, pday = prev
        if day == 1:
            assert (y, m) == ((py, pm + 1) if pm < 12 else (py + 1, 1))
            assert pday == (31 if pm <= 6 else 30 if pm <= 11 else pday) and pday in (29, 30, 31)
        else:
            assert (y, m, day) == (py, pm, pday + 1)
        prev, d = cur, d + timedelta(days=1)


def test_format_day():
    assert format_day("2026-11-08", "fa") == "۱۴۰۵/۰۸/۱۷"
    assert format_day("2026-11-08", "en") == "2026-11-08"
    # a moment is the day in Iran: 22:00 UTC is already the next day in Tehran
    assert format_day("2026-11-08T22:00:00Z", "fa") == "۱۴۰۵/۰۸/۱۸"
    assert format_day("2026-11-08T22:00:00", "fa") == "۱۴۰۵/۰۸/۱۸"
    assert format_day(datetime(2026, 11, 8, 22, tzinfo=UTC), "en") == "2026-11-08"
    assert format_day(None, "fa") == "—"
    assert format_day("soon", "fa") == "soon"
    assert fa_digits("20,574,439") == "۲۰,۵۷۴,۴۳۹"
