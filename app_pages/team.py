"""Team availability: everyone's busy blocks side by side, plus a free-slot finder."""

from __future__ import annotations

from datetime import date, time

import streamlit as st

from core import services
from core.calendar_ui import MEMBER_PALETTE, legend, occurrence_to_fc, preload_window, render_calendar
from core.ui import DATE_FORMAT, current_user, week_start

user = current_user()

members = services.list_members(include_inactive=False)
by_id = {m.id: m for m in members}
colors = {m.id: MEMBER_PALETTE[i % len(MEMBER_PALETTE)] for i, m in enumerate(members)}

# --------------------------------------------------------------------------- #
# Filters
# --------------------------------------------------------------------------- #
with st.container(horizontal=True, vertical_alignment="bottom"):
    selected = st.multiselect("Members", [m.id for m in members], default=[m.id for m in members],
                              format_func=lambda i: by_id[i].name, key="team_members", width=420)
    show_titles = st.toggle("Show entry titles", value=False, key="team_titles",
                            help="Off: only the member name and category are shown, which keeps details private.")
    week = st.date_input("Week of", value=week_start(date.today()), key="team_week", format=DATE_FORMAT)

if not selected:
    st.info("Select at least one member.")
    st.stop()

legend({by_id[i].name: colors[i] for i in selected})

# --------------------------------------------------------------------------- #
# Calendar with everyone overlaid
# --------------------------------------------------------------------------- #
anchor = week_start(week)
window_start, window_end = preload_window(anchor)

fc_events = []
for occ in services.occurrences_for_members(selected, window_start, window_end):
    name = by_id[occ.member_id].name
    title = f"{name}: {occ.title}" if show_titles else f"{name} · {occ.category}"
    fc_events.append(occurrence_to_fc(occ, title=title, color=colors[occ.member_id]))

render_calendar(fc_events, key="team_cal", initial_view="timeGridWeek", initial_date=anchor)

# --------------------------------------------------------------------------- #
# Free slot finder
# --------------------------------------------------------------------------- #
st.subheader("Find a time when everyone is free", anchor=False)
with st.container(horizontal=True, vertical_alignment="bottom"):
    day = st.date_input("Day", value=max(date.today(), anchor), key="team_free_day", format=DATE_FORMAT)
    hours = st.slider("Between", 0, 24, (8, 20), key="team_hours", format="%d:00", width=300)
    min_len = st.selectbox("At least", [15, 30, 60, 90, 120], index=1, key="team_min",
                           format_func=lambda m: f"{m} min", width=140)

slots = services.free_slots(selected, day, time(hours[0], 0), time(min(hours[1], 23), 59 if hours[1] == 24 else 0),
                            min_minutes=min_len)
if not slots:
    st.warning("No common free time on that day within the chosen hours.")
else:
    st.markdown(" ".join(f":green-badge[{s:%H:%M} - {e:%H:%M}]" for s, e in slots))
