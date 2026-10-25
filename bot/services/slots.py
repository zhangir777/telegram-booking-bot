"""Free slot calculation. Pure functions: no DB, no Telegram."""

from datetime import date, datetime, time, timedelta

Interval = tuple[datetime, datetime]


def parse_hm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def work_interval(schedule: dict, day: date) -> Interval | None:
    hours = schedule.get(str(day.weekday()))
    if not hours:
        return None
    return datetime.combine(day, parse_hm(hours[0])), datetime.combine(day, parse_hm(hours[1]))


def overlaps(a: Interval, b: Interval) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def free_slots(
    day: date,
    schedule: dict,
    duration_min: int,
    busy: list[Interval],
    now: datetime,
    step_min: int = 30,
    break_start: str | None = None,
    break_end: str | None = None,
) -> list[datetime]:
    """Start times on `day` where a service of `duration_min` fits.

    The visit must fit fully inside work hours, must not cross the break or any busy
    interval (bookings, blocked slots) and must start after `now`.
    """
    work = work_interval(schedule, day)
    if not work:
        return []
    blocked = list(busy)
    if break_start and break_end:
        blocked.append(
            (
                datetime.combine(day, parse_hm(break_start)),
                datetime.combine(day, parse_hm(break_end)),
            )
        )
    duration, step = timedelta(minutes=duration_min), timedelta(minutes=step_min)
    out, start = [], work[0]
    while start + duration <= work[1]:
        slot = (start, start + duration)
        if start > now and not any(overlaps(slot, b) for b in blocked):
            out.append(start)
        start += step
    return out
