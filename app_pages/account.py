"""My account: display name and password."""

from __future__ import annotations

import streamlit as st

from core import auth, services
from core.ui import current_user

user = current_user()

with st.container(border=True):
    st.subheader("Profile", anchor=False)
    st.text_input("Email", value=user.email, disabled=True)
    name = st.text_input("Display name", value=user.name, key="acct_name")
    if st.button("Save name", icon=":material/save:") and name.strip():
        services.update_member(user.id, display_name=name)
        st.session_state.user = auth.CurrentUser(user.id, user.email, name.strip(), user.is_admin)
        st.toast("Name updated.", icon=":material/check_circle:")
        st.rerun()

with st.container(border=True):
    st.subheader("Change password", anchor=False)
    with st.form("change_pw", border=False):
        current = st.text_input("Current password", type="password")
        new1 = st.text_input("New password", type="password")
        new2 = st.text_input("Confirm new password", type="password")
        if st.form_submit_button("Update password", type="primary", icon=":material/lock_reset:"):
            if new1 != new2:
                st.error("New passwords do not match.")
            elif error := auth.change_password(user.id, current, new1):
                st.error(error)
            else:
                st.success("Password changed.")
