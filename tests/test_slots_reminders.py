from datetime import date, datetime, timedelta

from bot.services.reminders import due_reminders, reminder_times
from bot.services.slots import free_slots

MON = date(2026, 11, 2)
SCHED = {"0": ["10:00", "13:00"]}
EARLY = datetime(2026, 11, 1, 12, 0)


def hm(slots):
    return [f"{s:%H:%M}" for s in slots]


def test_slots_fit_inside_work_hours():
    assert hm(free_slots(MON, SCHED, 60, [], EARLY)) == [
        "10:00",
        "10:30",
        "11:00",
        "11:30",
        "12:00",
    ]


def test_service_longer_than_day_has_no_slots():
    assert free_slots(MON, SCHED, 240, [], EARLY) == []


def test_day_off():
    assert free_slots(MON + timedelta(days=1), SCHED, 30, [], EARLY) == []


def test_break_is_respected():
    slots = free_slots(MON, {"0": ["10:00", "16:00"]}, 60, [], EARLY, 60, "13:00", "14:00")
    assert hm(slots) == ["10:00", "11:00", "12:00", "14:00", "15:00"]


def test_busy_interval_blocks_overlapping_slots():
    busy = [(datetime(2026, 11, 2, 11, 0), datetime(2026, 11, 2, 12, 0))]
    assert hm(free_slots(MON, SCHED, 60, busy, EARLY)) == ["10:00", "12:00"]


def test_past_slots_hidden():
    now = datetime(2026, 11, 2, 11, 10)
    assert hm(free_slots(MON, SCHED, 30, [], now)) == ["11:30", "12:00", "12:30"]


def test_step():
    assert hm(free_slots(MON, SCHED, 60, [], EARLY, step_min=60)) == ["10:00", "11:00", "12:00"]


def test_late_shift_until_midnight():
    slots = free_slots(MON, {"0": ["22:00", "23:59"]}, 60, [], EARLY, 60)
    assert hm(slots) == ["22:00"]


START = datetime(2026, 11, 5, 15, 0)


def test_reminder_times_both():
    times = reminder_times(START, created_at=START - timedelta(days=3))
    assert times == {"24h": START - timedelta(hours=24), "2h": START - timedelta(hours=2)}


def test_no_reminder_in_the_past():
    # booked 5 hours ahead: 24h reminder would be in the past
    assert list(reminder_times(START, START - timedelta(hours=5))) == ["2h"]
    assert reminder_times(START, START - timedelta(hours=1)) == {}


def test_due_reminders():
    created = START - timedelta(days=3)
    assert due_reminders(START, created, START - timedelta(hours=30), {}) == []
    assert due_reminders(START, created, START - timedelta(hours=23), {}) == ["24h"]
    assert due_reminders(START, created, START - timedelta(hours=23), {"24h": True}) == []
    assert due_reminders(START, created, START - timedelta(hours=1), {"24h": True}) == ["2h"]
    # bot was offline: only the closest reminder
    assert due_reminders(START, created, START - timedelta(hours=1), {}) == ["2h"]
    assert due_reminders(START, created, START + timedelta(minutes=1), {}) == []
