import asyncio
from datetime import date, datetime, timedelta

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from bot.db.models import Booking, Service
from bot.middlewares.common import AdminOnlyMiddleware
from bot.services import booking as svc
from bot.services.export import to_csv, to_xlsx
from bot.services.notify import broadcast

from .conftest import NOW

MON = date(2026, 11, 2)
T11 = datetime(2026, 11, 2, 11, 0)


async def test_double_booking_impossible(sm):
    """Two simultaneous requests for one slot: exactly one succeeds."""
    results = await asyncio.gather(
        svc.create_booking(sm, 10, 1, 1, T11, NOW),
        svc.create_booking(sm, 11, 1, 1, T11, NOW),
        return_exceptions=True,
    )
    ok = [r for r in results if isinstance(r, Booking)]
    taken = [r for r in results if isinstance(r, svc.SlotTaken)]
    assert len(ok) == 1 and len(taken) == 1


async def test_overlapping_booking_rejected(sm):
    await svc.create_booking(sm, 10, 1, 1, T11, NOW)
    with pytest.raises(svc.SlotTaken):
        await svc.create_booking(sm, 11, 1, 1, T11 + timedelta(minutes=30), NOW)


async def test_unique_index_is_last_line_of_defence(sm):
    from sqlalchemy.exc import IntegrityError

    async with sm() as s:
        s.add(
            Booking(user_id=10, master_id=1, service_id=1, start=T11, end=T11 + timedelta(hours=1))
        )
        await s.commit()
    with pytest.raises(IntegrityError):
        async with sm() as s:
            s.add(
                Booking(
                    user_id=11, master_id=1, service_id=1, start=T11, end=T11 + timedelta(hours=1)
                )
            )
            await s.commit()


async def test_any_master_falls_back_to_free_one(sm):
    await svc.create_booking(sm, 10, 1, 1, T11, NOW)
    async with sm() as s:
        service = await s.get(Service, 1)
        slots = await svc.available_slots(s, service, None, MON, NOW)
    assert slots[T11] == 2


async def test_cancel_frees_slot(sm):
    b = await svc.create_booking(sm, 10, 1, 1, T11, NOW)
    with pytest.raises(LookupError):
        await svc.cancel_booking(sm, b.id, user_id=11)  # someone else's booking
    await svc.cancel_booking(sm, b.id, user_id=10)
    assert await svc.create_booking(sm, 11, 1, 1, T11, NOW)


async def test_reschedule_frees_old_slot(sm):
    b = await svc.create_booking(sm, 10, 1, 1, T11, NOW)
    new = T11 + timedelta(hours=4)
    moved = await svc.reschedule_booking(sm, b.id, 10, new, NOW)
    assert moved.start == new and moved.end == new + timedelta(hours=1)
    assert await svc.create_booking(sm, 11, 1, 1, T11, NOW)


async def test_reschedule_to_taken_slot_fails(sm):
    b = await svc.create_booking(sm, 10, 1, 1, T11, NOW)
    other = T11 + timedelta(hours=4)
    await svc.create_booking(sm, 11, 1, 1, other, NOW)
    with pytest.raises(svc.SlotTaken):
        await svc.reschedule_booking(sm, b.id, 10, other, NOW)


async def test_reschedule_by_one_step_overlapping_itself(sm):
    b = await svc.create_booking(sm, 10, 1, 1, T11, NOW)
    moved = await svc.reschedule_booking(sm, b.id, 10, T11 + timedelta(minutes=30), NOW)
    assert moved.start == T11 + timedelta(minutes=30)


async def test_blocked_day_has_no_slots(sm):
    start = datetime.combine(MON, datetime.min.time())
    await svc.block_time(sm, None, start, start + timedelta(days=1), "holiday")
    async with sm() as s:
        assert await svc.available_slots(s, await s.get(Service, 1), None, MON, NOW) == {}
    with pytest.raises(svc.SlotTaken):
        await svc.create_booking(sm, 10, 1, 1, T11, NOW)


async def test_export(sm):
    await svc.create_booking(sm, 10, 1, 1, T11, NOW)
    async with sm() as s:
        items = await svc.bookings_between(s, T11 - timedelta(hours=1), T11 + timedelta(days=1))
    assert to_xlsx(items)[:2] == b"PK"
    assert "Cut" in to_csv(items).decode("utf-8-sig")


async def test_delete_user_data(sm):
    await svc.create_booking(sm, 10, 1, 1, T11, NOW)
    await svc.delete_user_data(sm, 10)
    async with sm() as s:
        assert await svc.user_bookings(s, 10, NOW) == []


class FakeUser:
    def __init__(self, uid):
        self.id = uid


async def test_admin_middleware_blocks_non_admin():
    mw = AdminOnlyMiddleware([1])
    calls = []

    async def handler(event, data):
        calls.append(data["event_from_user"].id)
        return "ok"

    assert await mw(handler, object(), {"event_from_user": FakeUser(2)}) is None
    assert await mw(handler, object(), {"event_from_user": FakeUser(1)}) == "ok"
    assert calls == [1]


async def test_broadcast_counts_blocked_users():
    async def send(uid):
        if uid == 2:
            raise TelegramForbiddenError(method=SendMessage(chat_id=2, text="x"), message="blocked")

    assert await broadcast(send, [1, 2, 3], rate=1000) == (2, 1)
