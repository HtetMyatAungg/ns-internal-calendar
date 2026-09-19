"""Small UI helpers shared by all pages."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import streamlit as st

from core.auth import CurrentUser


def current_user() -> CurrentUser:
    """The logged-in user. Pages are only reachable after login, so this never fails."""
    return st.session_state["user"]


def datetime_inputs(label_prefix: str, default_start: datetime, default_end: datetime,
                    key: str, all_day_default: bool = False) -> tuple[datetime, datetime, bool]:
    """Date/time pickers for a start-end range. Returns (start, end, all_day).

    For all-day items, `end` is the exclusive midnight after the last day, which is
    what FullCalendar expects.
    """
    all_day = st.checkbox("All day", value=all_day_default, key=f"{key}_allday")
    c1, c2 = st.columns(2)
    with c1:
        start_date = st.date_input(f"{label_prefix} start date", default_start.date(), key=f"{key}_sd")
        start_time = time(0, 0) if all_day else st.time_input(
            "Start time", default_start.time().replace(second=0, microsecond=0), key=f"{key}_st", step=900
        )
    with c2:
        end_default = (default_end - timedelta(days=1)).date() if all_day_default else default_end.date()
        end_date = st.date_input(f"{label_prefix} end date", max(end_default, start_date), key=f"{key}_ed")
        end_time = time(0, 0) if all_day else st.time_input(
            "End time", default_end.time().replace(second=0, microsecond=0), key=f"{key}_et", step=900
        )
    start = datetime.combine(start_date, start_time)
    end = datetime.combine(end_date + timedelta(days=1), time(0, 0)) if all_day else datetime.combine(end_date, end_time)
    return start, end, all_day


def fmt_range(start: datetime, end: datetime, all_day: bool) -> str:
    if all_day:
        last = (end - timedelta(days=1)).date()
        return f"{start:%a %d %b %Y}" if last == start.date() else f"{start:%a %d %b} - {last:%a %d %b %Y}"
    if start.date() == end.date():
        return f"{start:%a %d %b %Y}, {start:%H:%M} - {end:%H:%M}"
    return f"{start:%a %d %b %H:%M} - {end:%a %d %b %H:%M}"


def next_round_hour(now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    return (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())
