"""Application settings.

Values are read from Streamlit secrets (`.streamlit/secrets.toml` locally, or the
"Secrets" panel on Streamlit Community Cloud). Environment variables are used as a
fallback so the same code works in tests and scripts without Streamlit.

Expected secrets:

    [app]
    org_name = "NS"
    admin_emails = ["someone@yourorg.onmicrosoft.com"]

    [database]
    url = "postgresql://user:password@host/dbname?sslmode=require"
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

_URL_PASSWORD = re.compile(r"(://[^:/@\s]+:)[^@\s]+@")


def redact_secrets(text: str) -> str:
    """Hide passwords embedded in connection URLs before showing text to users."""
    return _URL_PASSWORD.sub(r"\1***@", text)


@dataclass(frozen=True)
class Settings:
    database_url: str
    org_name: str = "NS"
    admin_emails: tuple[str, ...] = field(default_factory=tuple)


def _read_secrets() -> dict:
    """Return Streamlit secrets as a plain dict, or {} if unavailable."""
    try:
        import streamlit as st

        return {k: st.secrets[k] for k in st.secrets}
    except Exception:
        return {}


def load_settings() -> Settings:
    secrets = _read_secrets()
    db = secrets.get("database", {})
    app = secrets.get("app", {})

    url = os.environ.get("DATABASE_URL") or db.get("url")
    if not url:
        raise RuntimeError(
            "No database configured. Set [database].url in .streamlit/secrets.toml "
            "or the DATABASE_URL environment variable."
        )

    admin_env = os.environ.get("ADMIN_EMAILS", "")
    admins = [e.strip() for e in admin_env.split(",") if e.strip()] or list(
        app.get("admin_emails", [])
    )

    return Settings(
        database_url=url,
        org_name=os.environ.get("ORG_NAME") or app.get("org_name", "NS"),
        admin_emails=tuple(a.lower() for a in admins),
    )
