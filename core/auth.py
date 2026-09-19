"""Login logic.

Access is allowlist based: an admin adds a member's Microsoft email first. The
member then logs in with that email and chooses a password on first visit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import bcrypt
from sqlalchemy import select

from core.db import session_scope
from core.models import Member

MIN_PASSWORD_LENGTH = 8


@dataclass(frozen=True)
class CurrentUser:
    """Snapshot of the logged-in member kept in session state."""

    id: int
    email: str
    name: str
    is_admin: bool


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def validate_password(password: str) -> str | None:
    """Return an error message, or None if the password is acceptable."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    return None


def find_member(email: str) -> Member | None:
    with session_scope() as db:
        return db.scalar(select(Member).where(Member.email == normalize_email(email)))


def lookup_status(email: str) -> str:
    """Classify an email for the login screen.

    Returns one of: "unknown", "inactive", "needs_password", "ready".
    """
    member = find_member(email)
    if member is None:
        return "unknown"
    if not member.is_active:
        return "inactive"
    return "ready" if member.has_password else "needs_password"


def set_password(email: str, password: str, display_name: str | None = None) -> CurrentUser:
    with session_scope() as db:
        member = db.scalar(select(Member).where(Member.email == normalize_email(email)))
        if member is None or not member.is_active:
            raise PermissionError("This email is not allowed to sign in.")
        member.password_hash = hash_password(password)
        if display_name is not None and display_name.strip():
            member.display_name = display_name.strip()
        member.last_login_at = datetime.now()
        db.flush()
        return _to_current_user(member)


def authenticate(email: str, password: str) -> CurrentUser | None:
    """Return the user on success, None on bad credentials or disallowed email."""
    with session_scope() as db:
        member = db.scalar(select(Member).where(Member.email == normalize_email(email)))
        if member is None or not member.is_active or not member.has_password:
            return None
        if not verify_password(password, member.password_hash or ""):
            return None
        member.last_login_at = datetime.now()
        return _to_current_user(member)


def change_password(member_id: int, current: str, new: str) -> str | None:
    """Return an error message, or None on success."""
    if error := validate_password(new):
        return error
    with session_scope() as db:
        member = db.get(Member, member_id)
        if member is None or not verify_password(current, member.password_hash or ""):
            return "Current password is incorrect."
        member.password_hash = hash_password(new)
    return None


def _to_current_user(member: Member) -> CurrentUser:
    return CurrentUser(id=member.id, email=member.email, name=member.name, is_admin=member.is_admin)
