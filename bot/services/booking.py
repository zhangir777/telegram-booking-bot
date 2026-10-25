"""Booking operations on the database. No aiogram imports, so it is testable without Telegram."""

import asyncio
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.db.models import BlockedSlot, Booking, Master, Service, User

from .slots import free_slots, overlaps

# Serializes booking writes inside the single bot process; the partial unique index
# in the DB is the second line of defence.
_write_lock = asyncio.Lock()


class SlotTaken(Exception):
    pass


async def get_or_create_user(s: AsyncSession, user_id: int, name: str = "") -> User:
    user = await s.get(User, user_id)
    if not user:
        user = User(id=user_id, name=name)
        s.add(user)
        await s.commit()
    return user


async def active_services(s: AsyncSession) -> list[Service]:
    return list(await s.scalars(select(Service).where(Service.active).order_by(Service.id)))


async def active_masters(s: AsyncSession) -> list[Master]:
    return list(await s.scalars(select(Master).where(Master.active).order_by(Master.id)))


async def busy_intervals(
    s: AsyncSession, master_id: int, day: date, exclude_booking: int | None = None
) -> list[tuple[datetime, datetime]]:
    day_start = datetime.combine(day, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    q = select(Booking.start, Booking.end).where(
        Booking.master_id == master_id,
        Booking.status == "active",
        Booking.start < day_end,
        Booking.end > day_start,
    )
    if exclude_booking:
        q = q.where(Booking.id != exclude_booking)
    blocks = select(BlockedSlot.start, BlockedSlot.end).where(
        (BlockedSlot.master_id == master_id) | (BlockedSlot.master_id.is_(None)),
        BlockedSlot.start < day_end,
        BlockedSlot.end > day_start,
    )
    return [tuple(r) for r in await s.execute(q)] + [tuple(r) for r in await s.execute(blocks)]


async def master_slots(
    s: AsyncSession,
    master: Master,
    service: Service,
    day: date,
    now: datetime,
    step: int = 30,
    exclude_booking: int | None = None,
) -> list[datetime]:
    busy = await busy_intervals(s, master.id, day, exclude_booking)
    return free_slots(
        day, master.schedule, service.duration_min, busy, now, step,
        master.break_start, master.break_end,
    )  # fmt: skip


async def available_slots(
    s: AsyncSession,
    service: Service,
    master_id: int | None,
    day: date,
    now: datetime,
    step: int = 30,
    exclude_booking: int | None = None,
) -> dict[datetime, int]:
    """{start time: master_id}. master_id None = any master (first free one wins)."""
    masters = await active_masters(s)
    if master_id:
        masters = [m for m in masters if m.id == master_id]
    out: dict[datetime, int] = {}
    for m in masters:
        for t in await master_slots(s, m, service, day, now, step, exclude_booking):
            out.setdefault(t, m.id)
    return dict(sorted(out.items()))


async def create_booking(
    sm: async_sessionmaker,
    user_id: int,
    master_id: int,
    service_id: int,
    start: datetime,
    now: datetime,
) -> Booking:
    """Re-checks the slot inside a lock + transaction. Raises SlotTaken if it is gone."""
    async with _write_lock, sm() as s, s.begin():
        service = await s.get(Service, service_id)
        master = await s.get(Master, master_id)
        if not service or not master or not service.active or not master.active:
            raise SlotTaken
        if start not in await master_slots(s, master, service, start.date(), now, step=5):
            raise SlotTaken
        booking = Booking(
            user_id=user_id,
            master_id=master_id,
            service_id=service_id,
            start=start,
            end=start + timedelta(minutes=service.duration_min),
            created_at=now,
        )
        s.add(booking)
        try:
            await s.flush()
        except IntegrityError as exc:
            raise SlotTaken from exc
    return booking


async def cancel_booking(sm: async_sessionmaker, booking_id: int, user_id: int | None) -> Booking:
    """user_id None = admin action."""
    async with _write_lock, sm() as s, s.begin():
        b = await s.get(Booking, booking_id)
        if not b or b.status != "active" or (user_id is not None and b.user_id != user_id):
            raise LookupError(booking_id)
        b.status = "cancelled"
    return b


async def reschedule_booking(
    sm: async_sessionmaker, booking_id: int, user_id: int, new_start: datetime, now: datetime
) -> Booking:
    async with _write_lock, sm() as s, s.begin():
        b = await s.get(Booking, booking_id)
        if not b or b.status != "active" or b.user_id != user_id:
            raise LookupError(booking_id)
        slots = await master_slots(
            s, b.master, b.service, new_start.date(), now, step=5, exclude_booking=b.id
        )
        if new_start not in slots:
            raise SlotTaken
        b.start, b.end = new_start, new_start + (b.end - b.start)
        b.reminded_24h = b.reminded_2h = b.confirmed = False
        b.created_at = now
    return b


async def user_bookings(s: AsyncSession, user_id: int, now: datetime) -> list[Booking]:
    q = (
        select(Booking)
        .where(Booking.user_id == user_id, Booking.status == "active", Booking.start > now)
        .order_by(Booking.start)
    )
    return list(await s.scalars(q))


async def bookings_between(
    s: AsyncSession, start: datetime, end: datetime, only_active: bool = True
) -> list[Booking]:
    q = select(Booking).where(Booking.start >= start, Booking.start < end).order_by(Booking.start)
    if only_active:
        q = q.where(Booking.status == "active")
    return list(await s.scalars(q))


async def block_time(
    sm: async_sessionmaker, master_id: int | None, start: datetime, end: datetime, reason: str
) -> None:
    async with _write_lock, sm() as s, s.begin():
        s.add(BlockedSlot(master_id=master_id, start=start, end=end, reason=reason))


def conflicts(bookings: list[Booking], start: datetime, end: datetime) -> list[Booking]:
    return [b for b in bookings if overlaps((b.start, b.end), (start, end))]


async def delete_user_data(sm: async_sessionmaker, user_id: int) -> None:
    """Privacy: remove the user and all their bookings."""
    async with _write_lock, sm() as s, s.begin():
        await s.execute(delete(Booking).where(Booking.user_id == user_id))
        await s.execute(delete(User).where(User.id == user_id))
