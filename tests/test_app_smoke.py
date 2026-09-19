"""Headless smoke test: run the real Streamlit app through login and every page."""

from __future__ import annotations

import os

import pytest
from streamlit.testing.v1 import AppTest

from core import auth, services

ROOT = os.path.dirname(os.path.dirname(__file__))


@pytest.fixture
def app(fresh_db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", fresh_db.database_url)
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    monkeypatch.chdir(ROOT)
    return AppTest.from_file(os.path.join(ROOT, "streamlit_app.py"), default_timeout=60)


def no_exceptions(at: AppTest) -> None:
    assert not at.exception, [e.value for e in at.exception]


def test_login_setup_and_pages(app: AppTest):
    at = app.run()
    no_exceptions(at)
    assert at.title[0].value.endswith("internal calendar")

    # Unknown email is rejected.
    at.text_input[0].set_value("nobody@example.com").run()
    assert any("not on the member list" in w.value for w in at.warning)

    # Seeded admin sets up a password.
    at.text_input[0].set_value("admin@example.com").run()
    assert any("First time here" in i.value for i in at.info)
    form_inputs = [t for t in at.text_input if t.label in ("Display name", "New password", "Confirm password")]
    form_inputs[0].set_value("Ada")
    form_inputs[1].set_value("supersecret")
    form_inputs[2].set_value("supersecret")
    at.button[0].click().run()
    no_exceptions(at)
    assert at.session_state["user"].name == "Ada"

    # Signed in: default page is "My calendar".
    assert at.title[0].value == "My calendar"
    no_exceptions(at)

    # Other pages render without errors.
    services.add_member("bob@example.com", "Bob")
    for page in ("app_pages/events.py", "app_pages/team.py", "app_pages/account.py", "app_pages/admin.py"):
        at.switch_page(page).run()
        no_exceptions(at)


def test_wrong_password(app: AppTest):
    auth.set_password("admin@example.com", "supersecret")
    at = app.run()
    at.text_input[0].set_value("admin@example.com").run()
    [pw] = [t for t in at.text_input if t.label == "Password"]
    pw.set_value("wrong")
    at.button[0].click().run()
    assert any("Incorrect password" in e.value for e in at.error)
    assert at.session_state["user"] is None
