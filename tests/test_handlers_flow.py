"""End-to-end booking flow through the real dispatcher with a fake Telegram API (no network)."""

import itertools
from datetime import datetime

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, Contact, Message, Update
from aiogram.types import User as TgUser

import bot.handlers.admin.panel as panel
import bot.handlers.client.booking as client
import bot.middlewares.common as mw
from bot.config import settings
from bot.db.models import Booking

ids = itertools.count(1)
USER = TgUser(id=10, is_bot=False, first_name="Test")
CHAT = Chat(id=10, type="private")


class FakeSession(BaseSession):
    """Records every API call and returns a plausible result."""

    def __init__(self):
        super().__init__()
        self.calls: list[TelegramMethod] = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if method.__returning__ in (bool, bool | Message, Message | bool):
            return True
        return Message(message_id=next(ids), date=datetime.now(), chat=CHAT, text="ok")

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""

    async def close(self):
        pass


def msg(text=None, contact=None):
    return Update(
        update_id=next(ids),
        message=Message(
            message_id=next(ids), date=datetime.now(), chat=CHAT, from_user=USER,
            text=text, contact=contact,
        ),
    )  # fmt: skip


def cb(data):
    m = Message(message_id=next(ids), date=datetime.now(), chat=CHAT, text="x")
    return Update(
        update_id=next(ids),
        callback_query=CallbackQuery(
            id=str(next(ids)), from_user=USER, chat_instance="1", message=m, data=data
        ),
    )


def buttons(call) -> list[str]:
    markup = call.reply_markup
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


@pytest.fixture
def env(sm, monkeypatch):
    for module in (client, panel, mw):
        monkeypatch.setattr(module, "Session", sm)
    for router in (client.router, panel.router):  # routers are module singletons
        monkeypatch.setattr(router, "_parent_router", None)
    monkeypatch.setattr(settings, "admin_ids", [99])
    monkeypatch.setattr(
        mw.ThrottleMiddleware,
        "__init__",
        lambda self, rate=0: (setattr(self, "rate", 0), setattr(self, "_last", {}))[-1],
    )
    from bot.main import build_dispatcher

    session = FakeSession()
    return build_dispatcher(), Bot("42:TEST", session=session), session


async def test_full_booking_flow(env, sm):
    dp, bot, api = env

    async def send(update):
        api.calls.clear()
        await dp.feed_update(bot, update)
        return [c for c in api.calls if hasattr(c, "reply_markup")]

    await send(msg("/start"))
    await send(cb("lang:en"))
    out = await send(cb("menu:book"))
    assert "svc:1" in buttons(out[-1])
    out = await send(cb("svc:1"))
    assert "mst:0" in buttons(out[-1])
    out = await send(cb("mst:0"))
    day = next(b for b in buttons(out[-1]) if b.startswith("day:"))
    out = await send(cb(day))
    time = next(b for b in buttons(out[-1]) if b.startswith("tm:"))
    out = await send(cb(time))
    assert "ok" in buttons(out[-1])
    out = await send(cb("ok"))
    assert out[-1].reply_markup.keyboard[0][0].request_contact  # phone is asked first
    await send(msg(contact=Contact(phone_number="+77001234567", first_name="T", user_id=10)))
    texts = [getattr(c, "text", "") for c in api.calls]
    assert any("You are booked" in t for t in texts)
    assert any(getattr(c, "chat_id", None) == 99 and "New booking" in c.text for c in api.calls)

    async with sm() as s:
        booking = await s.get(Booking, 1)
    assert booking.user.phone == "+77001234567" and booking.status == "active"

    await send(cb(f"bk:cancel:{booking.id}"))
    async with sm() as s:
        assert (await s.get(Booking, 1)).status == "cancelled"


async def test_admin_commands_hidden_from_clients(env):
    dp, bot, api = env
    await dp.feed_update(bot, msg("/admin"))
    assert not any("Admin panel" in getattr(c, "text", "") for c in api.calls)


async def test_foreign_booking_cannot_be_cancelled(env, sm):
    dp, bot, api = env
    from bot.services.booking import create_booking

    other = await create_booking(sm, 11, 1, 1, datetime(2030, 1, 7, 11, 0), datetime(2030, 1, 1))
    await dp.feed_update(bot, cb(f"bk:cancel:{other.id}"))
    async with sm() as s:
        assert (await s.get(Booking, other.id)).status == "active"


async def test_typed_phone_and_leaving_phone_step(env, sm):
    dp, bot, api = env

    async def send(update):
        api.calls.clear()
        await dp.feed_update(bot, update)
        return [c for c in api.calls if hasattr(c, "reply_markup")]

    async def reach_phone_step():
        await send(msg("/start"))
        await send(cb("lang:en"))
        await send(cb("menu:book"))
        await send(cb("svc:1"))
        out = await send(cb("mst:0"))
        out = await send(cb(next(b for b in buttons(out[-1]) if b.startswith("day:"))))
        await send(cb(next(b for b in buttons(out[-1]) if b.startswith("tm:"))))
        out = await send(cb("ok"))
        assert out[0].reply_markup is None  # confirm buttons removed, no double confirm
        assert out[-1].reply_markup.keyboard[0][0].request_contact

    await reach_phone_step()
    out = await send(msg("/start"))  # leaving the phone step hides the contact keyboard
    assert type(out[0].reply_markup).__name__ == "ReplyKeyboardRemove"

    await reach_phone_step()
    out = await send(msg("hello"))
    assert out[-1].reply_markup.keyboard[0][0].request_contact  # not a phone -> asked again
    await send(msg("8 (777) 123-45-67"))
    async with sm() as s:
        booking = await s.get(Booking, 1)
    assert booking.user.phone == "+77771234567" and booking.status == "active"


@pytest.mark.parametrize(
    ("raw", "phone"),
    [
        ("8 777 123 45 67", "+77771234567"),
        ("+7 (777) 123-45-67", "+77771234567"),
        ("77771234567", "+77771234567"),
        ("+1 415 555 0100", "+14155550100"),
        ("12345", None),
        ("hello", None),
    ],
)
def test_normalize_phone(raw, phone):
    assert client.normalize_phone(raw) == phone
