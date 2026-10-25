"""Reminder planning. A periodic job asks `due_reminders` what to send now.

Polling every minute (instead of one scheduled job per booking) survives restarts
and needs no job store.
"""

from datetime import datetime, timedelta

REMINDERS = {"24h": timedelta(hours=24), "2h": timedelta(hours=2)}


def reminder_times(start: datetime, created_at: datetime) -> dict[str, datetime]:
    """When to send each reminder. Skipped if that moment was already past at booking time
    (e.g. booked 3 hours ahead -> no 24h reminder, only 2h)."""
    return {kind: start - delta for kind, delta in REMINDERS.items() if start - delta > created_at}


def due_reminders(
    start: datetime, created_at: datetime, now: datetime, sent: dict[str, bool]
) -> list[str]:
    """Reminder kinds to send right now (time reached, visit not started, not sent yet)."""
    if now >= start:
        return []
    due = [
        kind
        for kind, at in reminder_times(start, created_at).items()
        if at <= now and not sent.get(kind)
    ]
    # If both are due (bot was offline), send only the closest one
    return due[-1:]
