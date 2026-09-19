"""All database reads/writes used by the pages.

Pages should call these functions instead of touching SQLAlchemy directly, so the
UI stays simple and the data rules live in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from core import feeds
from core.auth import normalize_email
from core.config import load_settings
from core.db import session_scope
from core.models import CalendarEntry, CalendarFeed, Event, Member, Rsvp
from core.recurrence import Occurrence, expand_entries

# --------------------------------------------------------------------------- #
# Members (allowlist)
# --------------------------------------------------------------------------- #


def ensure_admins(emails: tuple[str, ...] | list[str]) -> None:
    """Make sure every configured admin email exists and has admin rights."""
    if not emails:
        return
    with session_scope() as db:
        for raw in emails:
            email = normalize_email(raw)
            member = db.scalar(select(Member).where(Member.email == email))
            if member is None:
                db.add(Member(email=email, is_admin=True, is_active=True))
            else:
                member.is_admin = True
                member.is_active = True


def list_members(include_inactive: bool = True) -> list[Member]:
    with session_scope() as db:
        stmt = select(Member).order_by(Member.display_name, Member.email)
        if not include_inactive:
            stmt = stmt.where(Member.is_active.is_(True))
        return list(db.scalars(stmt))


def add_member(email: str, display_name: str = "", is_admin: bool = False) -> Member:
    email = normalize_email(email)
    if "@" not in email:
        raise ValueError(f"'{email}' is not a valid email address.")
    with session_scope() as db:
        existing = db.scalar(select(Member).where(Member.email == email))
        if existing is not None:
            raise ValueError(f"{email} is already a member.")
        member = Member(email=email, display_name=display_name.strip(), is_admin=is_admin)
        db.add(member)
        db.flush()
        return member


def add_members_bulk(text: str) -> tuple[list[str], list[str]]:
    """Add many emails at once (one per line or comma separated).

    Returns (added, skipped_with_reason).
    """
    added, skipped = [], []
    for raw in text.replace(",", "\n").replace(";", "\n").splitlines():
        email = raw.strip()
        if not email:
            continue
        try:
            add_member(email)
            added.append(normalize_email(email))
        except ValueError as exc:
            skipped.append(str(exc))
    return added, skipped


def update_member(member_id: int, *, display_name: str | None = None, is_admin: bool | None = None,
                  is_active: bool | None = None) -> None:
    with session_scope() as db:
        member = db.get(Member, member_id)
        if member is None:
            return
        if display_name is not None:
            member.display_name = display_name.strip()
        if is_admin is not None:
            member.is_admin = is_admin
        if is_active is not None:
            member.is_active = is_active


def reset_member_password(member_id: int) -> None:
    """Clear the password so the member sets a new one at next login."""
    with session_scope() as db:
        member = db.get(Member, member_id)
        if member is not None:
            member.password_hash = None


def delete_member(member_id: int) -> None:
    with session_scope() as db:
        member = db.get(Member, member_id)
        if member is not None:
            db.delete(member)


def count_admins() -> int:
    with session_scope() as db:
        return db.scalar(select(func.count()).select_from(Member).where(Member.is_admin.is_(True))) or 0


# --------------------------------------------------------------------------- #
# Personal calendar entries
# --------------------------------------------------------------------------- #


def list_entries(member_id: int) -> list[CalendarEntry]:
    with session_scope() as db:
        stmt = select(CalendarEntry).where(CalendarEntry.member_id == member_id).order_by(
            CalendarEntry.start_at
        )
        return list(db.scalars(stmt))


def get_entry(entry_id: int) -> CalendarEntry | None:
    with session_scope() as db:
        return db.get(CalendarEntry, entry_id)


def save_entry(member_id: int, data: dict, entry_id: int | None = None) -> CalendarEntry:
    """Create (entry_id=None) or update an entry owned by `member_id`."""
    _validate_range(data["start_at"], data["end_at"])
    with session_scope() as db:
        if entry_id is None:
            entry = CalendarEntry(member_id=member_id)
            db.add(entry)
        else:
            entry = db.get(CalendarEntry, entry_id)
            if entry is None or entry.member_id != member_id:
                raise PermissionError("You can only edit your own entries.")
        for field in ("title", "category", "start_at", "end_at", "all_day", "repeat",
                      "weekdays", "repeat_until", "notes"):
            if field in data:
                setattr(entry, field, data[field])
        db.flush()
        return entry


def delete_entry(member_id: int, entry_id: int) -> None:
    with session_scope() as db:
        entry = db.get(CalendarEntry, entry_id)
        if entry is not None and entry.member_id == member_id:
            db.delete(entry)


def occurrences_for_members(member_ids: list[int], window_start: datetime,
                            window_end: datetime) -> list[Occurrence]:
    """Expanded occurrences for the given members within the window."""
    if not member_ids:
        return []
    with session_scope() as db:
        stmt = select(CalendarEntry).where(CalendarEntry.member_id.in_(member_ids))
        # Cheap pre-filter: one-off entries entirely outside the window are skipped.
        stmt = stmt.where(
            (CalendarEntry.repeat != "none")
            | ((CalendarEntry.start_at < window_end) & (CalendarEntry.end_at > window_start))
        )
        entries = list(db.scalars(stmt))
        member_feeds = list(db.scalars(select(CalendarFeed).where(CalendarFeed.member_id.in_(member_ids))))

    occurrences = expand_entries(entries, window_start, window_end)
    occurrences += feed_occurrences_for(member_feeds, window_start, window_end)
    occurrences.sort(key=lambda o: o.start)
    return occurrences


# --------------------------------------------------------------------------- #
# Imported iCal feeds (e.g. university timetables)
# --------------------------------------------------------------------------- #


def list_feeds(member_id: int) -> list[CalendarFeed]:
    with session_scope() as db:
        return list(db.scalars(select(CalendarFeed).where(CalendarFeed.member_id == member_id)
                               .order_by(CalendarFeed.created_at)))


def add_feed(member_id: int, url: str, name: str = "", category: str = "Class") -> CalendarFeed:
    """Validate and download the feed once, then save it. Raises feeds.FeedError."""
    url = feeds.normalize_feed_url(url)
    data = feeds.download_feed(url)
    name = name.strip() or feeds.feed_name_from_data(data, "Imported calendar")
    with session_scope() as db:
        if db.scalar(select(CalendarFeed).where(CalendarFeed.member_id == member_id, CalendarFeed.url == url)):
            raise feeds.FeedError("You already subscribed to this calendar.")
        feed = CalendarFeed(member_id=member_id, url=url, name=name[:120], category=category)
        db.add(feed)
        db.flush()
        return feed


def delete_feed(member_id: int, feed_id: int) -> None:
    with session_scope() as db:
        feed = db.get(CalendarFeed, feed_id)
        if feed is not None and feed.member_id == member_id:
            db.delete(feed)


def feed_occurrences_for(member_feeds: list[CalendarFeed], window_start: datetime,
                         window_end: datetime) -> list[Occurrence]:
    """Occurrences from all given feeds. A broken feed is skipped (see feed_status)."""
    tz_name = load_settings().timezone
    # Feeds are queried by whole days (end exclusive); round out, then trim precisely.
    first_day, last_day = window_start.date(), window_end.date() + timedelta(days=1)
    result: list[Occurrence] = []
    for feed in member_feeds:
        try:
            events = feeds.load_feed_events(feed.url, first_day, last_day, tz_name)
        except feeds.FeedError:
            continue
        result += [
            o for o in feeds.feed_occurrences(feed.id, feed.member_id, feed.category, events)
            if o.start < window_end and o.end > window_start
        ]
    return result


def feed_status(feed: CalendarFeed) -> tuple[int, str | None]:
    """(number of events in the next 30 days, error message or None) for display."""
    today = date.today()
    try:
        events = feeds.load_feed_events(feed.url, today, today + timedelta(days=30), load_settings().timezone)
    except feeds.FeedError as exc:
        return 0, str(exc)
    return len(events), None


# --------------------------------------------------------------------------- #
# Shared events + RSVP
# --------------------------------------------------------------------------- #


@dataclass
class EventView:
    """An event plus its RSVP summary, ready for display."""

    event: Event
    going: list[str]
    maybe: list[str]
    not_going: list[str]
    my_status: str | None


def list_events(window_start: datetime | None = None, window_end: datetime | None = None,
                viewer_id: int | None = None) -> list[EventView]:
    with session_scope() as db:
        stmt = (
            select(Event)
            .options(selectinload(Event.rsvps).selectinload(Rsvp.member), selectinload(Event.created_by))
            .order_by(Event.start_at)
        )
        if window_start is not None:
            stmt = stmt.where(Event.end_at > window_start)
        if window_end is not None:
            stmt = stmt.where(Event.start_at < window_end)
        views = []
        for event in db.scalars(stmt):
            by_status: dict[str, list[str]] = {"going": [], "maybe": [], "not_going": []}
            my_status = None
            for r in event.rsvps:
                by_status.setdefault(r.status, []).append(r.member.name)
                if viewer_id is not None and r.member_id == viewer_id:
                    my_status = r.status
            views.append(EventView(event, by_status["going"], by_status["maybe"],
                                   by_status["not_going"], my_status))
        return views


def get_event(event_id: int) -> Event | None:
    with session_scope() as db:
        return db.scalar(select(Event).options(selectinload(Event.created_by)).where(Event.id == event_id))


def save_event(actor_id: int, actor_is_admin: bool, data: dict, event_id: int | None = None) -> Event:
    _validate_range(data["start_at"], data["end_at"])
    with session_scope() as db:
        if event_id is None:
            event = Event(created_by_id=actor_id)
            db.add(event)
        else:
            event = db.get(Event, event_id)
            if event is None:
                raise ValueError("Event not found.")
            if event.created_by_id != actor_id and not actor_is_admin:
                raise PermissionError("Only the creator or an admin can edit this event.")
        for field in ("title", "description", "location", "start_at", "end_at", "all_day"):
            if field in data:
                setattr(event, field, data[field])
        db.flush()
        return event


def delete_event(actor_id: int, actor_is_admin: bool, event_id: int) -> None:
    with session_scope() as db:
        event = db.get(Event, event_id)
        if event is None:
            return
        if event.created_by_id != actor_id and not actor_is_admin:
            raise PermissionError("Only the creator or an admin can delete this event.")
        db.delete(event)


def set_rsvp(member_id: int, event_id: int, status: str | None) -> None:
    """Set the member's RSVP; `status=None` removes it."""
    with session_scope() as db:
        rsvp = db.scalar(select(Rsvp).where(Rsvp.event_id == event_id, Rsvp.member_id == member_id))
        if status is None:
            if rsvp is not None:
                db.delete(rsvp)
        elif rsvp is None:
            db.add(Rsvp(event_id=event_id, member_id=member_id, status=status))
        else:
            rsvp.status = status


# --------------------------------------------------------------------------- #
# Team availability
# --------------------------------------------------------------------------- #


def free_slots(
    member_ids: list[int],
    day: date,
    day_start: time = time(8, 0),
    day_end: time = time(20, 0),
    min_minutes: int = 30,
) -> list[tuple[datetime, datetime]]:
    """Time ranges on `day` where none of the given members has an entry."""
    window_start = datetime.combine(day, day_start)
    window_end = datetime.combine(day, day_end)
    occurrences = occurrences_for_members(member_ids, window_start, window_end)
    if any(o.all_day for o in occurrences):
        return []
    busy = sorted((max(o.start, window_start), min(o.end, window_end)) for o in occurrences)

    slots: list[tuple[datetime, datetime]] = []
    cursor = window_start
    for start, end in busy:
        if start > cursor and start - cursor >= timedelta(minutes=min_minutes):
            slots.append((cursor, start))
        cursor = max(cursor, end)
    if window_end > cursor and window_end - cursor >= timedelta(minutes=min_minutes):
        slots.append((cursor, window_end))
    return slots


# --------------------------------------------------------------------------- #


def _validate_range(start_at: datetime, end_at: datetime) -> None:
    if end_at <= start_at:
        raise ValueError("End time must be after start time.")
