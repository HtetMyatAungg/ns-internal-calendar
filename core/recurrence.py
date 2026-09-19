"""Expand recurring calendar entries into concrete occurrences.

An entry stores one "template" (start, end, repeat rule). To draw it on a
calendar we need every occurrence inside the visible window. That is what
`expand_entry` does.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from core.models import CalendarEntry


@dataclass(frozen=True)
class Occurrence:
    """One block of time on a member's calendar.

    Comes either from a personal entry (`entry_id` set) or from an imported
    iCal feed (`feed_id` set). Feed occurrences are read-only in the UI.
    """

    member_id: int
    title: str
    category: str
    start: datetime
    end: datetime
    all_day: bool
    notes: str = ""
    entry_id: int | None = None
    feed_id: int | None = None
    location: str = ""


def expand_entry(entry: CalendarEntry, window_start: datetime, window_end: datetime) -> list[Occurrence]:
    """Return all occurrences of `entry` overlapping [window_start, window_end)."""
    duration = entry.end_at - entry.start_at
    if duration < timedelta(0):
        return []

    def make(day: date) -> Occurrence:
        start = datetime.combine(day, entry.start_at.time())
        return Occurrence(
            entry_id=entry.id,
            member_id=entry.member_id,
            title=entry.title,
            category=entry.category,
            start=start,
            end=start + duration,
            all_day=entry.all_day,
            notes=entry.notes or "",
        )

    def overlaps(occ: Occurrence) -> bool:
        return occ.start < window_end and occ.end > window_start

    if entry.repeat == "none":
        occ = make(entry.start_at.date())
        return [occ] if overlaps(occ) else []

    # Recurring: walk day by day from the later of (entry start, window start - duration)
    # up to the earlier of (repeat_until, window end).
    first_day = entry.start_at.date()
    last_day = window_end.date()
    if entry.repeat_until is not None:
        last_day = min(last_day, entry.repeat_until)
    day = max(first_day, (window_start - duration).date())
    weekdays = set(entry.weekday_list) if entry.repeat == "weekly" else None

    occurrences: list[Occurrence] = []
    while day <= last_day:
        if weekdays is None or day.weekday() in weekdays:
            occ = make(day)
            if overlaps(occ):
                occurrences.append(occ)
        day += timedelta(days=1)
    return occurrences


def expand_entries(
    entries: list[CalendarEntry], window_start: datetime, window_end: datetime
) -> list[Occurrence]:
    result: list[Occurrence] = []
    for entry in entries:
        result.extend(expand_entry(entry, window_start, window_end))
    result.sort(key=lambda o: o.start)
    return result


def describe_repeat(entry: CalendarEntry) -> str:
    """Human readable summary of the recurrence rule, e.g. 'Weekly on Mon, Wed'."""
    if entry.repeat == "none":
        return "Once"
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    text = "Daily" if entry.repeat == "daily" else "Weekly on " + ", ".join(
        names[d] for d in sorted(entry.weekday_list)
    )
    if entry.repeat_until:
        text += f" until {entry.repeat_until:%d %b %Y}"
    return text
