"""Import events from external iCal/ICS feeds (e.g. a university timetable).

A member pastes the subscription URL their institution gives them ("Add to
Outlook / Google Calendar" link). We download the feed, expand recurring events,
convert times to the organization's timezone and show them as read-only blocks
on the member's calendar. Feeds are re-downloaded at most every FEED_TTL.
"""

from __future__ import annotations

import functools
import ipaddress
import socket
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import certifi
import icalendar
import recurring_ical_events
import requests
import streamlit as st

from core.recurrence import Occurrence

FEED_TTL = "30m"
FETCH_TIMEOUT_SECONDS = 15
MAX_FEED_BYTES = 5 * 1024 * 1024


class FeedError(Exception):
    """Something is wrong with a feed URL or its contents (message is user-facing)."""


@dataclass(frozen=True)
class FeedEvent:
    """A single expanded event from a feed, in the organization's local time (naive)."""

    title: str
    start: datetime
    end: datetime
    all_day: bool
    location: str = ""
    description: str = ""


# --------------------------------------------------------------------------- #
# URL validation
# --------------------------------------------------------------------------- #


def normalize_feed_url(raw: str) -> str:
    """Accept http(s) and webcal URLs; reject anything that points inside our own network."""
    url = raw.strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise FeedError("Please paste a full link starting with https:// (or webcal://).")
    _reject_private_host(parsed.hostname)
    return url


def _reject_private_host(host: str) -> None:
    if host.lower() in ("localhost",) or host.endswith(".local"):
        raise FeedError("That address is not allowed.")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise FeedError(f"Could not find the server '{host}'.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise FeedError("That address is not allowed.")


# --------------------------------------------------------------------------- #
# Download + parse
# --------------------------------------------------------------------------- #


@functools.lru_cache(maxsize=1)
def ca_bundle() -> str:
    """Standard CA bundle plus any extra certificates in ./certs/*.pem.

    Some institution servers forget to send their intermediate certificate, so
    strict clients cannot verify them. Dropping the missing public intermediate
    into certs/ fixes that without disabling TLS verification.
    """
    extra = sorted(Path(__file__).resolve().parents[1].joinpath("certs").glob("*.pem"))
    if not extra:
        return certifi.where()
    bundle = Path(tempfile.gettempdir()) / "ns-internal-calendar-ca-bundle.pem"
    bundle.write_bytes(b"\n".join([Path(certifi.where()).read_bytes(), *(p.read_bytes() for p in extra)]))
    return str(bundle)


def download_feed(url: str) -> bytes:
    try:
        with requests.get(url, timeout=FETCH_TIMEOUT_SECONDS, stream=True, verify=ca_bundle(),
                          headers={"User-Agent": "NS-Internal-Calendar/1.0"}) as resp:
            resp.raise_for_status()
            data = resp.raw.read(MAX_FEED_BYTES + 1, decode_content=True)
    except requests.RequestException as exc:
        raise FeedError(f"Could not download the calendar: {exc.__class__.__name__}.") from exc
    if len(data) > MAX_FEED_BYTES:
        raise FeedError("The calendar file is too large.")
    if b"BEGIN:VCALENDAR" not in data[:4096]:
        raise FeedError("The link did not return a calendar (.ics) file.")
    return data


def parse_feed(data: bytes, window_start: date, window_end: date, tz_name: str) -> list[FeedEvent]:
    """Expand all events (including recurring ones) between the two dates."""
    try:
        calendar = icalendar.Calendar.from_ical(data)
        components = recurring_ical_events.of(calendar).between(window_start, window_end)
    except Exception as exc:  # noqa: BLE001 - library raises many ad-hoc types
        raise FeedError("The calendar file could not be read.") from exc

    tz = ZoneInfo(tz_name)
    events: list[FeedEvent] = []
    for comp in components:
        dtstart = comp.get("DTSTART")
        if dtstart is None:
            continue
        start_raw = dtstart.dt
        dtend = comp.get("DTEND")
        all_day = not isinstance(start_raw, datetime)
        if all_day:
            start = datetime.combine(start_raw, time.min)
            end = datetime.combine(dtend.dt, time.min) if dtend is not None else start + timedelta(days=1)
        else:
            start = _to_local(start_raw, tz)
            end = _to_local(dtend.dt, tz) if dtend is not None else start + timedelta(hours=1)
        if end <= start:
            continue
        events.append(FeedEvent(
            title=str(comp.get("SUMMARY") or "(untitled)").strip(),
            start=start,
            end=end,
            all_day=all_day,
            location=str(comp.get("LOCATION") or "").strip(),
            description=str(comp.get("DESCRIPTION") or "").strip(),
        ))
    events.sort(key=lambda e: e.start)
    return events


def _to_local(value: datetime, tz: ZoneInfo) -> datetime:
    """Convert an aware (or floating) datetime to naive local time."""
    if value.tzinfo is None:
        return value.replace(second=0, microsecond=0)
    return value.astimezone(tz).replace(tzinfo=None, second=0, microsecond=0)


def feed_name_from_data(data: bytes, fallback: str) -> str:
    """Use the calendar's own name (X-WR-CALNAME) when the member leaves the name blank."""
    try:
        name = icalendar.Calendar.from_ical(data).get("X-WR-CALNAME")
        return str(name).strip() if name else fallback
    except Exception:  # noqa: BLE001
        return fallback


# --------------------------------------------------------------------------- #
# Cached access used by the pages
# --------------------------------------------------------------------------- #


@st.cache_data(ttl=FEED_TTL, max_entries=200, show_spinner=False)
def load_feed_events(url: str, window_start: date, window_end: date, tz_name: str) -> list[FeedEvent]:
    """Download + parse, cached per URL/window so page reruns do not re-download."""
    return parse_feed(download_feed(url), window_start, window_end, tz_name)


def feed_occurrences(feed_id: int, member_id: int, category: str, events: list[FeedEvent]) -> list[Occurrence]:
    return [
        Occurrence(
            member_id=member_id, title=e.title, category=category, start=e.start, end=e.end,
            all_day=e.all_day, notes=e.description, feed_id=feed_id, location=e.location,
        )
        for e in events
    ]
