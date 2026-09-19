from datetime import date, datetime

import pytest

from core import feeds, services

# A small feed in the same style as the Royal Holloway timetable export, plus a
# weekly recurring event and an all-day event.
SAMPLE_ICS = b"""BEGIN:VCALENDAR
PRODID:-//Scientia Ltd//iCalendar Server v 1.0//EN
VERSION:2.0
X-WR-CALNAME:101115706 - AUNG, Htet Myat
X-WR-TIMEZONE:Europe/London
BEGIN:VEVENT
DTSTART;TZID=Europe/London:20270115T090000
DTEND;TZID=Europe/London:20270115T110000
UID:one
SUMMARY:CS2810 - Workshop - Online
LOCATION:
END:VEVENT
BEGIN:VEVENT
DTSTART:20270701T130000Z
DTEND:20270701T150000Z
UID:two
SUMMARY:Summer lecture (UTC, during BST)
LOCATION:WINDSOR-AUD
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=Europe/London:20270111T140000
DTEND;TZID=Europe/London:20270111T150000
RRULE:FREQ=WEEKLY;COUNT=3
UID:three
SUMMARY:Weekly seminar
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20270120
DTEND;VALUE=DATE:20270121
UID:four
SUMMARY:Reading day
END:VEVENT
END:VCALENDAR
"""


def test_parse_feed_expands_and_converts_to_local_time():
    events = feeds.parse_feed(SAMPLE_ICS, date(2027, 1, 1), date(2027, 12, 31), "Europe/London")
    titles = [e.title for e in events]
    assert titles.count("Weekly seminar") == 3
    workshop = next(e for e in events if e.title.startswith("CS2810"))
    assert workshop.start == datetime(2027, 1, 15, 9, 0) and workshop.end == datetime(2027, 1, 15, 11, 0)
    summer = next(e for e in events if e.title.startswith("Summer"))
    assert summer.start == datetime(2027, 7, 1, 14, 0)  # 13:00 UTC is 14:00 BST
    assert summer.location == "WINDSOR-AUD"
    reading = next(e for e in events if e.title == "Reading day")
    assert reading.all_day and reading.start == datetime(2027, 1, 20) and reading.end == datetime(2027, 1, 21)


def test_parse_feed_respects_window():
    events = feeds.parse_feed(SAMPLE_ICS, date(2027, 1, 11), date(2027, 1, 12), "Europe/London")
    assert [e.title for e in events] == ["Weekly seminar"]


def test_feed_name_from_data():
    assert feeds.feed_name_from_data(SAMPLE_ICS, "x") == "101115706 - AUNG, Htet Myat"
    assert feeds.feed_name_from_data(b"garbage", "fallback") == "fallback"


def test_normalize_feed_url():
    assert feeds.normalize_feed_url(" webcal://example.com/cal.ics ") == "https://example.com/cal.ics"
    with pytest.raises(feeds.FeedError):
        feeds.normalize_feed_url("not a url")
    with pytest.raises(feeds.FeedError):
        feeds.normalize_feed_url("http://localhost/cal.ics")
    with pytest.raises(feeds.FeedError):
        feeds.normalize_feed_url("http://127.0.0.1:55432/cal.ics")


def test_add_feed_and_occurrences(monkeypatch):
    monkeypatch.setattr(feeds, "download_feed", lambda url: SAMPLE_ICS)
    monkeypatch.setattr(feeds, "_reject_private_host", lambda host: None)
    feeds.load_feed_events.clear()
    member = services.add_member("a@x.com", "Alice")

    feed = services.add_feed(member.id, "https://timetable.example.edu/ical?p=1")
    assert feed.name == "101115706 - AUNG, Htet Myat" and feed.category == "Class"
    with pytest.raises(feeds.FeedError):
        services.add_feed(member.id, "https://timetable.example.edu/ical?p=1")

    occs = services.occurrences_for_members([member.id], datetime(2027, 1, 11), datetime(2027, 1, 18))
    assert [o.title for o in occs] == ["Weekly seminar", "CS2810 - Workshop - Online"]
    assert all(o.feed_id == feed.id and o.entry_id is None and o.category == "Class" for o in occs)

    # Imported classes count as busy time for the free-slot finder.
    from datetime import time
    slots = services.free_slots([member.id], date(2027, 1, 15), time(8), time(12))
    assert [(s.time(), e.time()) for s, e in slots] == [(time(8), time(9)), (time(11), time(12))]

    services.delete_feed(member.id, feed.id)
    assert services.list_feeds(member.id) == []


def test_broken_feed_is_skipped_not_fatal(monkeypatch):
    monkeypatch.setattr(feeds, "_reject_private_host", lambda host: None)
    monkeypatch.setattr(feeds, "download_feed", lambda url: SAMPLE_ICS)
    feeds.load_feed_events.clear()
    member = services.add_member("b@x.com", "Bob")
    feed = services.add_feed(member.id, "https://example.edu/ok.ics")

    def boom(url):
        raise feeds.FeedError("Could not download the calendar: ConnectionError.")

    monkeypatch.setattr(feeds, "download_feed", boom)
    feeds.load_feed_events.clear()
    assert services.occurrences_for_members([member.id], datetime(2027, 1, 1), datetime(2027, 2, 1)) == []
    count, error = services.feed_status(feed)
    assert count == 0 and "Could not download" in error
