"""Reporting periods. A period is a calendar month in local time."""

import datetime as dt
from dataclasses import dataclass

UTC_OFFSET_HOURS = 3


@dataclass(frozen=True)
class Period:
    start: dt.date  # inclusive
    end: dt.date    # exclusive

    @classmethod
    def parse(cls, text):
        """'2025-06' -> June 2025."""
        year, month = (int(part) for part in text.split("-"))
        start = dt.date(year, month, 1)
        end = dt.date(year + (month == 12), month % 12 + 1, 1)
        return cls(start, end)

    @property
    def label(self):
        return self.start.strftime("%Y-%m")

    @property
    def days(self):
        return (self.end - self.start).days

    def previous(self):
        last_day_of_previous = self.start - dt.timedelta(days=1)
        return Period.parse(last_day_of_previous.strftime("%Y-%m"))

    def sql_params(self):
        return {"period_start": self.start.isoformat(), "period_end": self.end.isoformat()}

    def utc_bounds(self):
        """The same period expressed against the raw UTC timestamp column."""
        offset = dt.timedelta(hours=UTC_OFFSET_HOURS)
        start = dt.datetime.combine(self.start, dt.time()) - offset
        end = dt.datetime.combine(self.end, dt.time()) - offset
        fmt = "%Y-%m-%d %H:%M:%S"
        return start.strftime(fmt), end.strftime(fmt)
