"""Messages to admins, broadcast with Telegram rate limits, reminder job."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.db.models import Booking
from bot.i18n import booking_details, t

from .reminders import due_reminders

log = logging.getLogger(__name__)
BROADCAST_RATE = 20  # messages per second, below Telegram's ~30/s limit


async def notify_admins(bot: Bot, admin_ids: Iterable[int], text: str) -> None:
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception as exc:  # admin blocked the bot, wrong id, etc.
            log.warning("Admin %s not notified: %s", admin_id, type(exc).__name__)


async def broadcast(
    send: Callable[[int], Awaitable[object]], user_ids: Iterable[int], rate: int = BROADCAST_RATE
) -> tuple[int, int]:
    """Send to all users with a rate limit. Returns (sent, failed)."""
    sent = failed = 0
    for uid in user_ids:
        for _ in range(2):
            try:
                await send(uid)
                sent += 1
                break
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after)
            except TelegramForbiddenError:
                failed += 1  # user blocked the bot
                break
            except Exception:
                failed += 1
                break
        else:
            failed += 1
        await asyncio.sleep(1 / rate)
    return sent, failed


async def send_due_reminders(bot: Bot, sm: async_sessionmaker, now: datetime, kb_factory) -> int:
    """Called every minute by APScheduler."""
    count = 0
    async with sm() as s, s.begin():
        q = select(Booking).where(
            Booking.status == "active",
            Booking.start > now,
            Booking.start <= now + timedelta(hours=24, minutes=5),
            or_(Booking.reminded_24h.is_(False), Booking.reminded_2h.is_(False)),
        )
        for b in await s.scalars(q):
            sent = {"24h": b.reminded_24h, "2h": b.reminded_2h}
            for kind in due_reminders(b.start, b.created_at, now, sent):
                lang = b.user.lang
                text = t(lang, f"remind_{kind}", details=booking_details(lang, b))
                try:
                    await bot.send_message(b.user_id, text, reply_markup=kb_factory(lang, b.id))
                    count += 1
                except Exception as exc:
                    log.warning("Reminder %s for booking %s failed: %s", kind, b.id, exc)
                # 2h implies the 24h one is no longer useful
                b.reminded_2h = b.reminded_2h or kind == "2h"
                b.reminded_24h = True
    return count
