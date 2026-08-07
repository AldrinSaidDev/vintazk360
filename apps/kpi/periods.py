"""Reporting periods: the `period` column of a CSV, both ways.

`db_schema.txt` Part D fixes one label format per cadence, and a KPI's
`frequency` decides which one it uses:

    daily      2026-07-15
    weekly     2026-W32          (ISO week)
    monthly    2026-07
    quarterly  2026-Q3
    annually   2026

`kpi_record` stores the period as a `period_start` / `period_end` pair rather
than that label, so the unique key `(kpi, period_start)` is what makes
re-uploading a corrected file update the month instead of duplicating it.
"""

from __future__ import annotations

import calendar
import datetime as dt
import re

from .models import Frequency


class PeriodError(ValueError):
    """A period cell that cannot be read. The message is user-facing."""


FORMAT_HINT = {
    Frequency.DAILY: 'YYYY-MM-DD (e.g. 2026-07-15)',
    Frequency.WEEKLY: 'YYYY-Www (e.g. 2026-W32)',
    Frequency.MONTHLY: 'YYYY-MM (e.g. 2026-07)',
    Frequency.QUARTERLY: 'YYYY-Qn (e.g. 2026-Q3)',
    Frequency.ANNUALLY: 'YYYY (e.g. 2026)',
}

_DAILY = re.compile(r'^(\d{4})-(\d{2})-(\d{2})$')
_WEEKLY = re.compile(r'^(\d{4})-W(\d{1,2})$', re.IGNORECASE)
_MONTHLY = re.compile(r'^(\d{4})-(\d{1,2})$')
_QUARTERLY = re.compile(r'^(\d{4})-Q([1-4])$', re.IGNORECASE)
_ANNUAL = re.compile(r'^(\d{4})$')

# A full ISO date, optionally with a time on the end. Spreadsheets love turning
# a period cell into a real date: type "2026-08" in Google Sheets or LibreOffice
# and it can come back as 2026-08-01, and openpyxl then hands us a datetime.
# Rejecting that would fail an upload over the spreadsheet's own autocorrect, so
# a date is read as the period CONTAINING it. Unambiguous at every cadence:
# 2026-08-06 is August for a monthly KPI, Q3 for a quarterly one, 2026 annually.
_ISO_DATE = re.compile(r'^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ]\d.*)?$')


def parse(cell: str, frequency: str) -> tuple[dt.date, dt.date]:
    """Turn a period cell into the `(period_start, period_end)` it names.

    The parameter is `cell`, not `label`: this function needs to call
    `label()` below, and a parameter of that name would shadow it.
    """
    text = (cell or '').strip()
    if not text:
        raise PeriodError('The period is missing.')

    try:
        if frequency == Frequency.DAILY:
            match = _DAILY.match(text)
            if match:
                day = dt.date(*(int(part) for part in match.groups()))
                return day, day

        elif frequency == Frequency.WEEKLY:
            match = _WEEKLY.match(text)
            if match:
                year, week = int(match.group(1)), int(match.group(2))
                start = dt.date.fromisocalendar(year, week, 1)
                return start, start + dt.timedelta(days=6)

        elif frequency == Frequency.QUARTERLY:
            match = _QUARTERLY.match(text)
            if match:
                year, quarter = int(match.group(1)), int(match.group(2))
                first = 3 * (quarter - 1) + 1
                return _month_span(year, first, months=3)

        elif frequency == Frequency.ANNUALLY:
            match = _ANNUAL.match(text)
            if match:
                year = int(match.group(1))
                return dt.date(year, 1, 1), dt.date(year, 12, 31)

        else:  # monthly, and the default for anything unrecognised
            match = _MONTHLY.match(text)
            if match:
                return _month_span(int(match.group(1)), int(match.group(2)))

        # Nothing matched this cadence's own format. Before giving up, accept a
        # full date and snap it to the period it falls in (see _ISO_DATE).
        iso = _ISO_DATE.match(text)
        if iso:
            day = dt.date(*(int(part) for part in iso.groups()[:3]))
            # `label()` always produces this cadence's exact format, so the
            # recursion is one level deep and cannot loop.
            return parse(label(day, frequency), frequency)

    except ValueError as error:
        # A well-formed but impossible date, e.g. 2026-02-30 or week 54.
        raise PeriodError(f'"{text}" is not a real date ({error}).')

    raise PeriodError(
        f'"{text}" is not a valid {frequency} period. '
        f'Use {FORMAT_HINT.get(frequency, FORMAT_HINT[Frequency.MONTHLY])}.'
    )


def _month_span(year: int, month: int, months: int = 1) -> tuple[dt.date, dt.date]:
    start = dt.date(year, month, 1)
    last_month = month + months - 1
    year_end, month_end = year + (last_month - 1) // 12, (last_month - 1) % 12 + 1
    return start, dt.date(year_end, month_end, calendar.monthrange(year_end, month_end)[1])


def label(start: dt.date, frequency: str) -> str:
    """The inverse of `parse`: how this period reads in a CSV or on screen."""
    if frequency == Frequency.DAILY:
        return start.isoformat()
    if frequency == Frequency.WEEKLY:
        iso = start.isocalendar()
        return f'{iso.year}-W{iso.week:02d}'
    if frequency == Frequency.QUARTERLY:
        return f'{start.year}-Q{(start.month - 1) // 3 + 1}'
    if frequency == Frequency.ANNUALLY:
        return str(start.year)
    return f'{start.year}-{start.month:02d}'


def current(frequency: str, today: dt.date | None = None) -> tuple[dt.date, dt.date]:
    """The period we are inside right now, for form defaults."""
    return parse(label(today or dt.date.today(), frequency), frequency)
