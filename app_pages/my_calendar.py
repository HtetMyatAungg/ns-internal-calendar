"""My calendar: view, add, edit and delete personal schedule entries."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from core import services
from core.calendar_ui import event_to_fc, legend, occurrence_to_fc, preload_window, render_calendar
from core.feeds import FeedError
from core.models import CATEGORIES, EVENT_COLOR, CalendarEntry
from core.recurrence import describe_repeat
from core.ui import DATE_FORMAT, current_user, datetime_inputs, fmt_range, next_round_hour

user = current_user()
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
st.session_state.setdefault("mycal_selected_entry", None)


# --------------------------------------------------------------------------- #
# Entry form (used for both "add" and "edit")
# --------------------------------------------------------------------------- #
def entry_form(existing: CalendarEntry | None, key: str) -> None:
    defaults_start = existing.start_at if existing else next_round_hour()
    defaults_end = existing.end_at if existing else defaults_start + timedelta(hours=1)

    title = st.text_input("Title", value=existing.title if existing else "", key=f"{key}_title",
                          placeholder="e.g. Shift at front desk, CS101 lecture")
    category = st.selectbox("Category", list(CATEGORIES), key=f"{key}_cat",
                            index=list(CATEGORIES).index(existing.category) if existing else 0)
    start, end, all_day = datetime_inputs("Entry", defaults_start, defaults_end, key=key,
                                          all_day_default=existing.all_day if existing else False)

    repeat = st.segmented_control(
        "Repeat", ["none", "daily", "weekly"], default=existing.repeat if existing else "none",
        format_func=lambda v: {"none": "Does not repeat", "daily": "Daily", "weekly": "Weekly"}[v],
        key=f"{key}_repeat",
    ) or "none"
    weekdays: list[int] = []
    repeat_until: date | None = None
    if repeat == "weekly":
        chosen = st.pills("On days", WEEKDAY_NAMES, selection_mode="multi", key=f"{key}_days",
                          default=[WEEKDAY_NAMES[d] for d in existing.weekday_list] if existing and existing.weekdays
                          else [WEEKDAY_NAMES[start.weekday()]])
        weekdays = sorted(WEEKDAY_NAMES.index(d) for d in chosen)
    if repeat != "none":
        has_end = st.checkbox("Stop repeating on a date", key=f"{key}_hasend",
                              value=bool(existing and existing.repeat_until))
        if has_end:
            repeat_until = st.date_input("Last day", key=f"{key}_until", format=DATE_FORMAT,
                                         value=existing.repeat_until if existing and existing.repeat_until
                                         else start.date() + timedelta(weeks=12))
    notes = st.text_area("Notes", value=existing.notes if existing else "", key=f"{key}_notes", height=80)

    with st.container(horizontal=True, horizontal_alignment="right"):
        if existing is not None and st.button("Delete", icon=":material/delete:", key=f"{key}_del"):
            services.delete_entry(user.id, existing.id)
            st.session_state.mycal_selected_entry = None
            st.toast("Entry deleted.")
            st.rerun()
        if st.button("Save", type="primary", icon=":material/save:", key=f"{key}_save"):
            if not title.strip():
                st.error("Please enter a title.")
                return
            if repeat == "weekly" and not weekdays:
                st.error("Pick at least one weekday.")
                return
            try:
                services.save_entry(
                    user.id,
                    {"title": title.strip(), "category": category, "start_at": start, "end_at": end,
                     "all_day": all_day, "repeat": repeat, "weekdays": ",".join(map(str, weekdays)),
                     "repeat_until": repeat_until, "notes": notes.strip()},
                    entry_id=existing.id if existing else None,
                )
            except ValueError as exc:
                st.error(str(exc))
                return
            st.session_state.mycal_selected_entry = None
            st.toast("Saved.", icon=":material/check_circle:")
            st.rerun()


# --------------------------------------------------------------------------- #
# Imported iCal feeds (university timetable, Outlook/Google "publish" links, ...)
# --------------------------------------------------------------------------- #
def feed_manager() -> None:
    st.markdown("**Subscribe to a calendar link**")
    st.caption("Paste the iCal / ICS link your university or calendar app gives you "
               "(the one meant for *Outlook on the web* or *Google Calendar*). "
               "Its events will appear here automatically and stay up to date.")
    with st.form("add_feed", border=False, clear_on_submit=True):
        url = st.text_input("Calendar link", placeholder="https://.../ical/...  or  webcal://...")
        c1, c2 = st.columns(2)
        name = c1.text_input("Name (optional)", placeholder="e.g. Uni timetable")
        category = c2.selectbox("Show as", list(CATEGORIES), index=list(CATEGORIES).index("Class"))
        if st.form_submit_button("Subscribe", type="primary", icon=":material/add_link:"):
            try:
                with st.spinner("Checking the calendar link..."):
                    feed = services.add_feed(user.id, url, name, category)
            except FeedError as exc:
                st.error(str(exc))
            else:
                st.toast(f"Subscribed to {feed.name}.", icon=":material/check_circle:")
                st.rerun()

    my_feeds = services.list_feeds(user.id)
    if my_feeds:
        st.markdown("**Your subscriptions**")
    for feed in my_feeds:
        count, error = services.feed_status(feed)
        with st.container(horizontal=True, vertical_alignment="center"):
            status = f":red[{error}]" if error else f"{count} events in the next 30 days"
            st.markdown(f"**{feed.name}** · {feed.category}  \n{status}")
            st.space()
            if st.button("Remove", key=f"rm_feed_{feed.id}", icon=":material/link_off:"):
                services.delete_feed(user.id, feed.id)
                st.rerun()


# --------------------------------------------------------------------------- #
# Toolbar
# --------------------------------------------------------------------------- #
with st.container(horizontal=True, vertical_alignment="center"):
    view = st.segmented_control("View", ["timeGridWeek", "dayGridMonth", "listWeek"], default="timeGridWeek",
                                format_func=lambda v: {"timeGridWeek": "Week", "dayGridMonth": "Month",
                                                       "listWeek": "List"}[v],
                                key="mycal_view", label_visibility="collapsed")
    show_events = st.toggle("Show shared events", value=True, key="mycal_show_events")
    st.space()
    with st.popover("Import timetable", icon=":material/rss_feed:"):
        feed_manager()
    with st.popover("Add entry", icon=":material/add:", type="primary"):
        entry_form(None, key="new")

legend({**CATEGORIES, "Shared event": EVENT_COLOR})

# --------------------------------------------------------------------------- #
# Calendar
# --------------------------------------------------------------------------- #
window_start, window_end = preload_window()

fc_events = [occurrence_to_fc(o) for o in services.occurrences_for_members([user.id], window_start, window_end)]
if show_events:
    fc_events += [event_to_fc(v) for v in services.list_events(window_start, window_end, viewer_id=user.id)]

clicked = render_calendar(fc_events, key="mycal", initial_view=view or "timeGridWeek")
if clicked is not None:
    kind, item_id = clicked
    if kind == "entry":
        st.session_state.mycal_selected_entry = item_id
    elif kind == "feed":
        st.session_state.mycal_selected_entry = None
        st.info("This comes from an imported calendar link, so it can't be edited here. "
                "Use *Import timetable* to manage your subscriptions.", icon=":material/rss_feed:")
    else:
        st.session_state.mycal_selected_entry = None
        ev = services.get_event(item_id)
        if ev is not None:
            st.info(f"**{ev.title}** - shared event, {fmt_range(ev.start_at, ev.end_at, ev.all_day)}. "
                    "Open the *Shared events* page to RSVP.", icon=":material/celebration:")

# --------------------------------------------------------------------------- #
# Edit selected entry
# --------------------------------------------------------------------------- #
selected_id = st.session_state.mycal_selected_entry
if selected_id is not None:
    entry = services.get_entry(selected_id)
    if entry is None or entry.member_id != user.id:
        st.session_state.mycal_selected_entry = None
    else:
        with st.container(border=True):
            st.subheader(f"Edit: {entry.title}", anchor=False)
            st.caption(f"{fmt_range(entry.start_at, entry.end_at, entry.all_day)} · {describe_repeat(entry)}")
            entry_form(entry, key=f"edit_{entry.id}")
            if st.button("Close", icon=":material/close:", key="close_edit"):
                st.session_state.mycal_selected_entry = None
                st.rerun()

# --------------------------------------------------------------------------- #
# Plain list (handy on mobile, and for entries far in the future)
# --------------------------------------------------------------------------- #
with st.expander("All my entries", icon=":material/list:"):
    entries = services.list_entries(user.id)
    if not entries:
        st.caption("No entries yet. Use *Add entry* above to log your work hours, classes, etc.")
    for e in entries:
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{e.title}** · {e.category}  \n{fmt_range(e.start_at, e.end_at, e.all_day)} · {describe_repeat(e)}")
            st.space()
            if st.button("Edit", key=f"list_edit_{e.id}", icon=":material/edit:"):
                st.session_state.mycal_selected_entry = e.id
                st.rerun()
