from datetime import date, datetime

from core.models import CalendarEntry
from core.recurrence import describe_repeat, expand_entry


def make(**kwargs) -> CalendarEntry:
    base = dict(id=1, member_id=1, title="Shift", category="Work",
                start_at=datetime(2026, 9, 7, 9, 0), end_at=datetime(2026, 9, 7, 12, 0),
                all_day=False, repeat="none", weekdays="", repeat_until=None, notes="")
    return CalendarEntry(**{**base, **kwargs})


WINDOW = (datetime(2026, 9, 7), datetime(2026, 9, 21))  # two weeks, Mon 7 Sep -> Mon 21 Sep


def test_single_entry_inside_window():
    occs = expand_entry(make(), *WINDOW)
    assert len(occs) == 1
    assert occs[0].start == datetime(2026, 9, 7, 9, 0)
    assert occs[0].end == datetime(2026, 9, 7, 12, 0)


def test_single_entry_outside_window():
    assert expand_entry(make(start_at=datetime(2026, 10, 1, 9), end_at=datetime(2026, 10, 1, 10)), *WINDOW) == []


def test_weekly_on_mon_wed():
    occs = expand_entry(make(repeat="weekly", weekdays="0,2"), *WINDOW)
    assert [o.start.date() for o in occs] == [date(2026, 9, 7), date(2026, 9, 9), date(2026, 9, 14), date(2026, 9, 16)]
    assert all(o.start.time() == datetime(2026, 9, 7, 9).time() for o in occs)


def test_weekly_respects_repeat_until():
    occs = expand_entry(make(repeat="weekly", weekdays="0", repeat_until=date(2026, 9, 10)), *WINDOW)
    assert [o.start.date() for o in occs] == [date(2026, 9, 7)]


def test_daily_starts_at_entry_start_not_window_start():
    occs = expand_entry(make(repeat="daily", start_at=datetime(2026, 9, 10, 8), end_at=datetime(2026, 9, 10, 9)), *WINDOW)
    assert occs[0].start.date() == date(2026, 9, 10)
    assert len(occs) == 11  # 10 Sep .. 20 Sep inclusive


def test_overnight_entry_overlapping_window_start_is_included():
    entry = make(start_at=datetime(2026, 9, 6, 22), end_at=datetime(2026, 9, 7, 2))
    assert len(expand_entry(entry, *WINDOW)) == 1


def test_describe_repeat():
    assert describe_repeat(make()) == "Once"
    assert describe_repeat(make(repeat="daily")) == "Daily"
    assert describe_repeat(make(repeat="weekly", weekdays="0,4", repeat_until=date(2026, 12, 1))) == \
        "Weekly on Mon, Fri until 01 Dec 2026"
