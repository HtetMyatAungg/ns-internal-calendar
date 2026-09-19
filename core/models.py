"""Database tables (SQLAlchemy ORM).

Five tables:
- members          : who may log in (allowlist). Admins add rows here.
- calendar_entries : a member's personal schedule (work shifts, classes, ...).
- calendar_feeds   : external iCal/ICS subscriptions (e.g. a university timetable)
                     whose events are shown on the member's calendar.
- events           : shared events visible to everyone.
- rsvps            : a member's response to a shared event.

All timestamps are stored as naive "organization local time".
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Personal entry categories and their calendar colours.
CATEGORIES: dict[str, str] = {
    "Work": "#1d4ed8",
    "Class": "#15803d",
    "Personal": "#7e22ce",
    "Unavailable": "#b91c1c",
    "Other": "#6b7280",
}
EVENT_COLOR = "#ea580c"

REPEAT_OPTIONS = ("none", "daily", "weekly")
RSVP_OPTIONS = ("going", "maybe", "not_going")


class Base(DeclarativeBase):
    pass


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    # NULL until the member sets a password on first login.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    entries: Mapped[list["CalendarEntry"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )
    feeds: Mapped[list["CalendarFeed"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )

    @property
    def name(self) -> str:
        return self.display_name or self.email.split("@")[0]

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None


class CalendarEntry(Base):
    __tablename__ = "calendar_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40), default="Work")
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    # Recurrence: "none" | "daily" | "weekly". For weekly, `weekdays` is a
    # comma-separated list of ISO weekday numbers (0=Mon ... 6=Sun).
    repeat: Mapped[str] = mapped_column(String(10), default="none")
    weekdays: Mapped[str] = mapped_column(String(20), default="")
    repeat_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    member: Mapped[Member] = relationship(back_populates="entries")

    @property
    def weekday_list(self) -> list[int]:
        return [int(d) for d in self.weekdays.split(",") if d.strip() != ""]


class CalendarFeed(Base):
    __tablename__ = "calendar_feeds"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(String(2000))
    # Category used to colour the imported events.
    category: Mapped[str] = mapped_column(String(40), default="Class")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    member: Mapped[Member] = relationship(back_populates="feeds")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("members.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    created_by: Mapped[Member | None] = relationship()
    rsvps: Mapped[list["Rsvp"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class Rsvp(Base):
    __tablename__ = "rsvps"
    __table_args__ = (UniqueConstraint("event_id", "member_id", name="uq_rsvp_event_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(10))  # going | maybe | not_going
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    event: Mapped[Event] = relationship(back_populates="rsvps")
    member: Mapped[Member] = relationship()
