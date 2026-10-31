import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

from bot.db.session import Session
from bot.i18n import t
from bot.services.booking import get_or_create_user


class UserLangMiddleware(BaseMiddleware):
    """Loads (or creates) the user and puts `user` and `lang` into handler data."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user:
            async with Session() as s:
                user = await get_or_create_user(s, tg_user.id, tg_user.full_name)
            data["user"], data["lang"] = user, user.lang
        return await handler(event, data)


class AdminOnlyMiddleware(BaseMiddleware):
    """Silently drops updates from non-admins (attach to the admin router)."""

    def __init__(self, admin_ids: list[int]):
        self.admin_ids = set(admin_ids)

    async def __call__(self, handler, event, data):
        tg_user = data.get("event_from_user")
        if not tg_user or tg_user.id not in self.admin_ids:
            if isinstance(event, CallbackQuery):
                await event.answer()
            return None
        return await handler(event, data)


class ThrottleMiddleware(BaseMiddleware):
    """Anti-flood: at most one update per `rate` seconds per user."""

    def __init__(self, rate: float = 0.5):
        self.rate = rate
        self._last: dict[int, float] = {}

    async def __call__(self, handler, event, data):
        tg_user = data.get("event_from_user")
        if tg_user:
            now = time.monotonic()
            if now - self._last.get(tg_user.id, 0) < self.rate:
                if isinstance(event, CallbackQuery):
                    await event.answer(t(data.get("lang", "en"), "too_fast"))
                return None  # messages are ignored silently
            self._last[tg_user.id] = now
        return await handler(event, data)
