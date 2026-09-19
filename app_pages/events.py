"""Shared events: everyone sees them, anyone can create one, members RSVP."""

from __future__ import annotations

from datetime import datetime, timedelta

import streamlit as st

from core import services
from core.calendar_ui import event_to_fc, render_calendar
from core.models import Event
from core.services import EventView
from core.ui import current_user, datetime_inputs, fmt_range, next_round_hour

user = current_user()
st.session_state.setdefault("events_editing", None)

RSVP_LABELS = {"going": "Going", "maybe": "Maybe", "not_going": "Can't go"}


# --------------------------------------------------------------------------- #
# Create / edit form
# --------------------------------------------------------------------------- #
def event_form(existing: Event | None, key: str) -> None:
    start_default = existing.start_at if existing else next_round_hour()
    end_default = existing.end_at if existing else start_default + timedelta(hours=2)

    title = st.text_input("Title", value=existing.title if existing else "", key=f"{key}_title")
    location = st.text_input("Location", value=existing.location if existing else "", key=f"{key}_loc",
                             placeholder="Room, address or meeting link")
    start, end, all_day = datetime_inputs("Event", start_default, end_default, key=key,
                                          all_day_default=existing.all_day if existing else False)
    description = st.text_area("Description", value=existing.description if existing else "",
                               key=f"{key}_desc", height=100)

    with st.container(horizontal=True, horizontal_alignment="right"):
        if existing is not None and st.button("Delete", icon=":material/delete:", key=f"{key}_del"):
            services.delete_event(user.id, user.is_admin, existing.id)
            st.session_state.events_editing = None
            st.toast("Event deleted.")
            st.rerun()
        if st.button("Save", type="primary", icon=":material/save:", key=f"{key}_save"):
            if not title.strip():
                st.error("Please enter a title.")
                return
            try:
                services.save_event(
                    user.id, user.is_admin,
                    {"title": title.strip(), "location": location.strip(), "description": description.strip(),
                     "start_at": start, "end_at": end, "all_day": all_day},
                    event_id=existing.id if existing else None,
                )
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))
                return
            st.session_state.events_editing = None
            st.toast("Event saved.", icon=":material/check_circle:")
            st.rerun()


def can_edit(view: EventView) -> bool:
    return user.is_admin or view.event.created_by_id == user.id


def event_card(view: EventView) -> None:
    e = view.event
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"### {e.title}")
            st.space()
            if can_edit(view) and st.button("Edit", key=f"edit_{e.id}", icon=":material/edit:", type="tertiary"):
                st.session_state.events_editing = e.id
                st.rerun()
        details = fmt_range(e.start_at, e.end_at, e.all_day)
        if e.location:
            details += f" · :material/location_on: {e.location}"
        if e.created_by is not None:
            details += f" · by {e.created_by.name}"
        st.caption(details)
        if e.description:
            st.write(e.description)

        with st.container(horizontal=True, vertical_alignment="center"):
            choice = st.segmented_control(
                "Your RSVP", list(RSVP_LABELS), default=view.my_status, format_func=RSVP_LABELS.get,
                key=f"rsvp_{e.id}", label_visibility="collapsed",
            )
            if choice != view.my_status:
                services.set_rsvp(user.id, e.id, choice)
                st.rerun()
            st.space()
            st.markdown(
                f":green-badge[:material/check: {len(view.going)} going] "
                f":orange-badge[:material/question_mark: {len(view.maybe)} maybe] "
                f":red-badge[:material/close: {len(view.not_going)} can't go]"
            )
        if view.going or view.maybe:
            with st.expander("Who's coming"):
                if view.going:
                    st.markdown("**Going:** " + ", ".join(view.going))
                if view.maybe:
                    st.markdown("**Maybe:** " + ", ".join(view.maybe))
                if view.not_going:
                    st.markdown("**Can't go:** " + ", ".join(view.not_going))


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
with st.container(horizontal=True, vertical_alignment="center"):
    mode = st.segmented_control("Display", ["Upcoming", "Calendar", "Past"], default="Upcoming",
                                key="events_mode", label_visibility="collapsed")
    st.space()
    with st.popover("New event", icon=":material/add:", type="primary"):
        event_form(None, key="new_event")

editing_id = st.session_state.events_editing
if editing_id is not None:
    ev = services.get_event(editing_id)
    if ev is None:
        st.session_state.events_editing = None
    else:
        with st.container(border=True):
            st.subheader(f"Edit: {ev.title}", anchor=False)
            event_form(ev, key=f"edit_event_{ev.id}")
            if st.button("Close", icon=":material/close:", key="close_event_edit"):
                st.session_state.events_editing = None
                st.rerun()

now = datetime.now()
if mode == "Calendar":
    views = services.list_events(now - timedelta(days=90), now + timedelta(days=365), viewer_id=user.id)
    clicked = render_calendar([event_to_fc(v) for v in views], key="events_cal", initial_view="dayGridMonth")
    if clicked is not None and clicked[0] == "event":
        match = [v for v in views if v.event.id == clicked[1]]
        if match:
            event_card(match[0])
elif mode == "Past":
    views = [v for v in services.list_events(window_end=now, viewer_id=user.id)]
    views.reverse()
    if not views:
        st.caption("No past events.")
    for v in views[:30]:
        event_card(v)
else:
    views = services.list_events(window_start=now, viewer_id=user.id)
    if not views:
        st.info("No upcoming events. Create one with *New event*.", icon=":material/event:")
    for v in views:
        event_card(v)
