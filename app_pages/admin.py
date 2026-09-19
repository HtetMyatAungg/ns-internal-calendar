"""Admin: manage who can sign in.

Add Microsoft emails here; those people can then log in and set a password.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import services
from core.ui import current_user

user = current_user()
if not user.is_admin:
    st.error("Admins only.")
    st.stop()

# --------------------------------------------------------------------------- #
# Add members
# --------------------------------------------------------------------------- #
with st.container(border=True):
    st.subheader("Add members", anchor=False)
    st.caption("Enter the Microsoft emails of people who may use the calendar. "
               "They will choose a password the first time they sign in.")
    tab_one, tab_many = st.tabs(["One person", "Several at once"])
    with tab_one, st.form("add_one", border=False, clear_on_submit=True):
        email = st.text_input("Email", placeholder="name@yourorg.onmicrosoft.com", autocomplete="off")
        display_name = st.text_input("Display name (optional)")
        make_admin = st.checkbox("Make admin")
        if st.form_submit_button("Add member", type="primary", icon=":material/person_add:"):
            try:
                services.add_member(email, display_name, make_admin)
                st.success(f"Added {email.strip().lower()}.")
            except ValueError as exc:
                st.error(str(exc))
    with tab_many, st.form("add_many", border=False, clear_on_submit=True):
        text = st.text_area("Emails", height=140,
                            placeholder="one@yourorg.com\ntwo@yourorg.com\nthree@yourorg.com",
                            help="One per line, or separated by commas.")
        if st.form_submit_button("Add all", type="primary", icon=":material/group_add:"):
            added, skipped = services.add_members_bulk(text)
            if added:
                st.success(f"Added {len(added)}: " + ", ".join(added))
            for reason in skipped:
                st.warning(reason)

# --------------------------------------------------------------------------- #
# Member table (editable)
# --------------------------------------------------------------------------- #
st.subheader("Members", anchor=False)
members = services.list_members()
admin_count = services.count_admins()

df = pd.DataFrame(
    [{
        "id": m.id,
        "Email": m.email,
        "Display name": m.display_name,
        "Admin": m.is_admin,
        "Active": m.is_active,
        "Password set": m.has_password,
        "Last login": m.last_login_at,
    } for m in members]
)

if df.empty:
    st.caption("No members yet.")
    st.stop()

edited = st.data_editor(
    df,
    key="members_editor",
    hide_index=True,
    disabled=["id", "Email", "Password set", "Last login"],
    column_config={
        "id": None,
        "Admin": st.column_config.CheckboxColumn(help="Admins can manage members and any event."),
        "Active": st.column_config.CheckboxColumn(help="Inactive members cannot sign in."),
        "Last login": st.column_config.DatetimeColumn(format="DD MMM YYYY HH:mm"),
    },
)

changes = edited[(edited["Display name"] != df["Display name"]) | (edited["Admin"] != df["Admin"])
                 | (edited["Active"] != df["Active"])]
if not changes.empty and st.button("Save changes", type="primary", icon=":material/save:"):
    for _, row in changes.iterrows():
        if int(row["id"]) == user.id and (not row["Admin"] or not row["Active"]):
            st.error("You cannot remove your own admin rights or deactivate yourself.")
            continue
        services.update_member(int(row["id"]), display_name=row["Display name"],
                               is_admin=bool(row["Admin"]), is_active=bool(row["Active"]))
    st.toast("Members updated.", icon=":material/check_circle:")
    st.rerun()

# --------------------------------------------------------------------------- #
# Per-member actions
# --------------------------------------------------------------------------- #
with st.expander("Reset password or remove a member", icon=":material/manage_accounts:"):
    others = [m for m in members if m.id != user.id]
    if not others:
        st.caption("No other members.")
    else:
        target_id = st.selectbox("Member", [m.id for m in others],
                                 format_func=lambda i: next(m.email for m in others if m.id == i),
                                 key="admin_target")
        with st.container(horizontal=True):
            if st.button("Reset password", icon=":material/lock_reset:",
                         help="Clears their password; they choose a new one at next sign-in."):
                services.reset_member_password(target_id)
                st.toast("Password reset.")
                st.rerun()
            confirm = st.checkbox("I understand this also deletes their calendar entries", key="confirm_delete")
            if st.button("Remove member", icon=":material/person_remove:", disabled=not confirm):
                services.delete_member(target_id)
                st.toast("Member removed.")
                st.rerun()

st.caption(f"{len(members)} members · {admin_count} admins")
