"""Helpers to draw a FullCalendar widget (via `streamlit-calendar`).

Event ids are prefixed so a click can be traced back to the right table:
    "entry-<id>"  -> personal calendar entry
    "event-<id>"  -> shared event
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import streamlit as st
from streamlit_calendar import calendar

from core.models import CATEGORIES, EVENT_COLOR
from core.recurrence import Occurrence
from core.services import EventView

# Distinct colours for members on the team view.
MEMBER_PALETTE = [
    "#1d4ed8", "#15803d", "#b45309", "#7e22ce", "#0e7490",
    "#be123c", "#4d7c0f", "#6d28d9", "#c2410c", "#0f766e",
]

BASE_OPTIONS = {
    "headerToolbar": {
        "left": "prev,next today",
        "center": "title",
        "right": "dayGridMonth,timeGridWeek,listWeek",
    },
    "initialView": "timeGridWeek",
    "slotMinTime": "06:00:00",
    "slotMaxTime": "23:00:00",
    "firstDay": 1,
    "nowIndicator": True,
    "navLinks": True,
    "weekNumbers": False,
    "height": 720,
    "expandRows": True,
    "allDaySlot": True,
    "eventTimeFormat": {"hour": "2-digit", "minute": "2-digit", "hour12": False},
}


def occurrence_to_fc(occ: Occurrence, title: str | None = None, color: str | None = None) -> dict:
    return {
        "id": f"entry-{occ.entry_id}",
        "title": title or occ.title,
        "start": _fmt(occ.start, occ.all_day),
        "end": _fmt(occ.end, occ.all_day),
        "allDay": occ.all_day,
        "backgroundColor": color or CATEGORIES.get(occ.category, CATEGORIES["Other"]),
        "borderColor": color or CATEGORIES.get(occ.category, CATEGORIES["Other"]),
    }


def event_to_fc(view: EventView) -> dict:
    e = view.event
    title = e.title if view.my_status != "going" else f"{e.title} (going)"
    return {
        "id": f"event-{e.id}",
        "title": title,
        "start": _fmt(e.start_at, e.all_day),
        "end": _fmt(e.end_at, e.all_day),
        "allDay": e.all_day,
        "backgroundColor": EVENT_COLOR,
        "borderColor": EVENT_COLOR,
    }


def render_calendar(events: list[dict], key: str, initial_view: str = "timeGridWeek",
                    initial_date: date | None = None, **option_overrides) -> tuple[str, int] | None:
    """Draw the calendar. Returns ("entry"|"event", id) when the user clicks an item."""
    options = {**BASE_OPTIONS, "initialView": initial_view, **option_overrides}
    if initial_date is not None:
        options["initialDate"] = initial_date.isoformat()
    state = calendar(events=events, options=options, callbacks=["eventClick"], key=key)
    clicked = (state or {}).get("eventClick", {}).get("event", {}).get("id")
    if clicked and "-" in clicked:
        kind, raw_id = clicked.split("-", 1)
        if raw_id.isdigit():
            return kind, int(raw_id)
    return None


def visible_window(anchor: date, view: str) -> tuple[datetime, datetime]:
    """A generous window of data to load around the anchor date for a given view."""
    if view == "dayGridMonth":
        start = anchor.replace(day=1) - timedelta(days=7)
        end = start + timedelta(days=7 * 7)
    else:
        start = anchor - timedelta(days=anchor.weekday() + 7)
        end = start + timedelta(days=21)
    return datetime.combine(start, datetime.min.time()), datetime.combine(end, datetime.min.time())


def legend(items: dict[str, str]) -> None:
    """Small colour legend rendered with badges."""
    st.markdown(" ".join(f":{_badge_color(c)}-badge[{name}]" for name, c in items.items()))


def _badge_color(hex_color: str) -> str:
    # Streamlit badges accept named colours only; map our palette to the closest.
    mapping = {
        "#1d4ed8": "blue", "#15803d": "green", "#7e22ce": "violet", "#b91c1c": "red",
        "#6b7280": "gray", "#ea580c": "orange", "#b45309": "orange", "#0e7490": "blue",
        "#be123c": "red", "#4d7c0f": "green", "#6d28d9": "violet", "#c2410c": "orange",
        "#0f766e": "green",
    }
    return mapping.get(hex_color, "gray")


def _fmt(value: datetime, all_day: bool) -> str:
    return value.date().isoformat() if all_day else value.strftime("%Y-%m-%dT%H:%M:%S")
