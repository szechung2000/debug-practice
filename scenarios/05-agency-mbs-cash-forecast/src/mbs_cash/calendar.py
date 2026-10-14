"""Business-day calendar for agency MBS payments (Fedwire / Federal Reserve holidays)."""
from __future__ import annotations

import csv
import logging
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)


class CalendarError(Exception):
    pass


class BusinessCalendar:
    def __init__(self, holidays: set[date], name: str = "FED"):
        self.name = name
        self.holidays = frozenset(holidays)
        if self.holidays:
            self.first_year = min(h.year for h in self.holidays)
            self.last_year = max(h.year for h in self.holidays)
        else:
            self.first_year = self.last_year = 0

    @classmethod
    def from_csv(cls, path: Path) -> "BusinessCalendar":
        """File format: date,name  (ISO dates, '#' starts a comment line)."""
        if not path.exists():
            raise CalendarError(f"holiday file not found: {path}")
        holidays: set[date] = set()
        with path.open(newline="") as fh:
            for line_no, row in enumerate(csv.reader(fh), start=1):
                if not row or row[0].strip().startswith("#") or row[0].strip().lower() == "date":
                    continue
                try:
                    holidays.add(date.fromisoformat(row[0].strip()))
                except ValueError as exc:
                    raise CalendarError(f"{path.name} line {line_no}: bad date {row[0]!r}") from exc
        log.info("calendar: %d holidays %s-%s", len(holidays),
                 min(holidays).year if holidays else "-", max(holidays).year if holidays else "-")
        return cls(holidays)

    def covers(self, d: date) -> bool:
        return self.first_year <= d.year <= self.last_year

    def is_business_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays

    def roll_forward(self, d: date) -> date:
        """Following business day convention."""
        if not self.covers(d):
            raise CalendarError(f"{self.name} calendar has no holidays for {d.year}")
        for _ in range(10):
            if self.is_business_day(d):
                return d
            d = d + timedelta(days=1)
        raise CalendarError(f"no business day within 10 days of {d}")

    def add_business_days(self, d: date, n: int) -> date:
        step = 1 if n >= 0 else -1
        remaining = abs(n)
        while remaining:
            d = d + timedelta(days=step)
            if self.is_business_day(d):
                remaining -= 1
        return d
