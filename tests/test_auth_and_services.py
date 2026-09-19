from datetime import date, datetime, time

import pytest

from core import auth, services


def test_admin_seeded_and_can_set_password():
    assert auth.lookup_status("Admin@Example.com") == "needs_password"
    user = auth.set_password("admin@example.com", "supersecret", "Ada")
    assert user.is_admin and user.name == "Ada"
    assert auth.lookup_status("admin@example.com") == "ready"
    assert auth.authenticate("admin@example.com", "supersecret") is not None
    assert auth.authenticate("admin@example.com", "wrong") is None


def test_unknown_email_cannot_log_in():
    assert auth.lookup_status("stranger@example.com") == "unknown"
    with pytest.raises(PermissionError):
        auth.set_password("stranger@example.com", "supersecret")


def test_bulk_add_members_and_deactivate():
    added, skipped = services.add_members_bulk("a@x.com, B@x.com\nadmin@example.com\nnot-an-email")
    assert added == ["a@x.com", "b@x.com"]
    assert len(skipped) == 2
    member = next(m for m in services.list_members() if m.email == "a@x.com")
    services.update_member(member.id, is_active=False)
    assert auth.lookup_status("a@x.com") == "inactive"


def test_change_password_requires_current():
    auth.set_password("admin@example.com", "supersecret")
    admin = auth.authenticate("admin@example.com", "supersecret")
    assert auth.change_password(admin.id, "nope", "anothersecret") == "Current password is incorrect."
    assert auth.change_password(admin.id, "supersecret", "short") is not None
    assert auth.change_password(admin.id, "supersecret", "anothersecret") is None
    assert auth.authenticate("admin@example.com", "anothersecret") is not None


def _two_members():
    a = services.add_member("a@x.com", "Alice")
    b = services.add_member("b@x.com", "Bob")
    return a, b


def test_entries_are_private_to_owner():
    a, b = _two_members()
    entry = services.save_entry(a.id, {"title": "Shift", "category": "Work",
                                       "start_at": datetime(2026, 9, 7, 9), "end_at": datetime(2026, 9, 7, 12),
                                       "all_day": False, "repeat": "none", "weekdays": "", "repeat_until": None,
                                       "notes": ""})
    with pytest.raises(PermissionError):
        services.save_entry(b.id, {"title": "Hijack", "start_at": entry.start_at, "end_at": entry.end_at}, entry.id)
    services.delete_entry(b.id, entry.id)  # silently ignored
    assert len(services.list_entries(a.id)) == 1
    with pytest.raises(ValueError):
        services.save_entry(a.id, {"title": "Bad", "start_at": datetime(2026, 9, 7, 9), "end_at": datetime(2026, 9, 7, 8)})


def test_free_slots_across_members():
    a, b = _two_members()
    day = date(2026, 9, 8)  # Tuesday
    services.save_entry(a.id, {"title": "Class", "category": "Class", "start_at": datetime(2026, 9, 8, 9),
                               "end_at": datetime(2026, 9, 8, 11), "all_day": False, "repeat": "weekly",
                               "weekdays": "1", "repeat_until": None, "notes": ""})
    services.save_entry(b.id, {"title": "Work", "category": "Work", "start_at": datetime(2026, 9, 8, 13),
                               "end_at": datetime(2026, 9, 8, 15), "all_day": False, "repeat": "none",
                               "weekdays": "", "repeat_until": None, "notes": ""})
    slots = services.free_slots([a.id, b.id], day, time(8), time(17))
    assert [(s.time(), e.time()) for s, e in slots] == [
        (time(8), time(9)), (time(11), time(13)), (time(15), time(17)),
    ]


def test_events_and_rsvp():
    a, b = _two_members()
    event = services.save_event(a.id, False, {"title": "Town hall", "description": "", "location": "Room 1",
                                              "start_at": datetime(2026, 10, 1, 10), "end_at": datetime(2026, 10, 1, 11),
                                              "all_day": False})
    services.set_rsvp(a.id, event.id, "going")
    services.set_rsvp(b.id, event.id, "maybe")
    services.set_rsvp(b.id, event.id, "going")  # update, not duplicate
    [view] = services.list_events(viewer_id=b.id)
    assert sorted(view.going) == ["Alice", "Bob"] and view.maybe == [] and view.my_status == "going"
    services.set_rsvp(b.id, event.id, None)
    [view] = services.list_events(viewer_id=b.id)
    assert view.going == ["Alice"] and view.my_status is None

    with pytest.raises(PermissionError):
        services.delete_event(b.id, False, event.id)
    services.delete_event(b.id, True, event.id)  # admin may delete
    assert services.list_events() == []
