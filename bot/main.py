import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import settings
from bot.db.session import Session, engine, init_db
from bot.handlers.admin.panel import router as admin_router
from bot.handlers.client.booking import now
from bot.handlers.client.booking import router as client_router
from bot.keyboards.builders import reminder_kb
from bot.middlewares.common import AdminOnlyMiddleware, ThrottleMiddleware, UserLangMiddleware
from bot.services.notify import send_due_reminders


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(ThrottleMiddleware())
        observer.middleware(UserLangMiddleware())
    admin_router.message.middleware(AdminOnlyMiddleware(settings.admin_ids))
    admin_router.callback_query.middleware(AdminOnlyMiddleware(settings.admin_ids))
    dp.include_routers(admin_router, client_router)
    return dp


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN is empty: copy .env.example to .env and set it")
    await init_db(engine)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    async def reminder_job() -> None:
        await send_due_reminders(bot, Session, now(), reminder_kb)

    scheduler.add_job(reminder_job, "interval", minutes=1)
    scheduler.start()
    try:
        await build_dispatcher().start_polling(bot)
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
