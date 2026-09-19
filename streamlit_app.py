"""NS Internal Calendar - entry point.

Run locally with:  streamlit run streamlit_app.py

Flow: connect to the database -> require login -> show the pages.
"""

from __future__ import annotations

import streamlit as st

from core import auth
from core.config import load_settings
from core.db import init_db

st.set_page_config(page_title="NS Internal Calendar", page_icon=":material/calendar_month:", layout="wide")


@st.cache_resource(show_spinner="Connecting to database...")
def _startup() -> str:
    """Runs once per server process: create tables and seed admin accounts."""
    settings = load_settings()
    init_db(settings)
    return settings.org_name


org_name = _startup()
st.session_state.setdefault("user", None)


# --------------------------------------------------------------------------- #
# Login screen (shown until the user is signed in)
# --------------------------------------------------------------------------- #
def login_screen() -> None:
    _, center, _ = st.columns([1, 1.2, 1])
    with center, st.container(border=True):
        st.title(f"{org_name} internal calendar", anchor=False)
        st.caption("Sign in with the Microsoft email your admin registered.")

        email = st.text_input("Email", key="login_email", placeholder="you@yourorg.com", autocomplete="email")
        status = auth.lookup_status(email) if "@" in email else None

        if status == "unknown":
            st.warning("This email is not on the member list. Ask an admin to add you.")
        elif status == "inactive":
            st.error("This account has been deactivated. Contact an admin.")
        elif status == "needs_password":
            st.info("First time here? Choose a password to finish setting up your account.")
            with st.form("setup", border=False):
                name = st.text_input("Display name", placeholder="How teammates will see you")
                pw1 = st.text_input("New password", type="password")
                pw2 = st.text_input("Confirm password", type="password")
                if st.form_submit_button("Create account", type="primary", icon=":material/person_add:"):
                    if error := auth.validate_password(pw1):
                        st.error(error)
                    elif pw1 != pw2:
                        st.error("Passwords do not match.")
                    else:
                        st.session_state.user = auth.set_password(email, pw1, name)
                        st.rerun()
        elif status == "ready":
            with st.form("login", border=False):
                pw = st.text_input("Password", type="password")
                if st.form_submit_button("Sign in", type="primary", icon=":material/login:"):
                    user = auth.authenticate(email, pw)
                    if user is None:
                        st.error("Incorrect password.")
                    else:
                        st.session_state.user = user
                        st.rerun()


if st.session_state.user is None:
    login_screen()
    st.stop()


# --------------------------------------------------------------------------- #
# Signed in: navigation
# --------------------------------------------------------------------------- #
user: auth.CurrentUser = st.session_state.user

pages = {
    "": [
        st.Page("app_pages/my_calendar.py", title="My calendar", icon=":material/calendar_today:", default=True),
        st.Page("app_pages/events.py", title="Shared events", icon=":material/celebration:"),
        st.Page("app_pages/team.py", title="Team availability", icon=":material/groups:"),
    ],
    "Settings": [st.Page("app_pages/account.py", title="My account", icon=":material/person:")],
}
if user.is_admin:
    pages["Settings"].append(st.Page("app_pages/admin.py", title="Members (admin)", icon=":material/admin_panel_settings:"))

page = st.navigation(pages, position="sidebar")

with st.sidebar:
    st.caption(f"Signed in as **{user.name}**  \n{user.email}")
    if st.button("Sign out", icon=":material/logout:", width="stretch"):
        st.session_state.user = None
        st.rerun()

st.title(page.title, anchor=False)
page.run()
