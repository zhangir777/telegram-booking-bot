"""Lightweight FAQ + lead bot (aiogram 3). For quick orders: edit faq.yaml and .env.

Run: uv run python -m template.bot
"""

import asyncio
import logging
import os
import re
from pathlib import Path

import yaml
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

CONFIG = yaml.safe_load(Path(__file__).with_name("faq.yaml").read_text(encoding="utf-8"))
router = Router()


class FaqCb(CallbackData, prefix="faq"):
    index: int  # -1 = leave a lead


class Lead(StatesGroup):
    name = State()
    phone = State()
    comment = State()


def normalize_phone(raw: str) -> str | None:
    """+7XXXXXXXXXX for KZ/RU numbers written as 8..., +7..., 7..., with spaces/brackets."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    return None


def menu_kb():
    kb = InlineKeyboardBuilder()
    for i, item in enumerate(CONFIG["faq"]):
        kb.button(text=item["q"], callback_data=FaqCb(index=i))
    kb.button(text=CONFIG["lead_button"], callback_data=FaqCb(index=-1))
    return kb.adjust(1).as_markup()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(CONFIG["greeting"], reply_markup=menu_kb())


@router.callback_query(FaqCb.filter(F.index >= 0))
async def faq(call: CallbackQuery, callback_data: FaqCb):
    items = CONFIG["faq"]
    if callback_data.index >= len(items):
        return await call.answer()
    item = items[callback_data.index]
    await call.message.answer(f"<b>{item['q']}</b>\n{item['a']}", reply_markup=menu_kb())
    await call.answer()


@router.callback_query(FaqCb.filter(F.index == -1))
async def lead_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(Lead.name)
    await call.message.answer(CONFIG["texts"]["ask_name"])
    await call.answer()


@router.message(Lead.name, F.text)
async def lead_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text[:100])
    await state.set_state(Lead.phone)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=CONFIG["texts"]["share_phone"], request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(CONFIG["texts"]["ask_phone"], reply_markup=kb)


@router.message(Lead.phone)
async def lead_phone(message: Message, state: FSMContext):
    raw = message.contact.phone_number if message.contact else (message.text or "")
    phone = normalize_phone(raw)
    if not phone:
        return await message.answer(CONFIG["texts"]["ask_phone"])
    await state.update_data(phone=phone)
    await state.set_state(Lead.comment)
    await message.answer(CONFIG["texts"]["ask_comment"], reply_markup=ReplyKeyboardRemove())


@router.message(Lead.comment, F.text)
async def lead_comment(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    user = message.from_user
    text = (
        f"📝 New lead\nName: {data['name']}\nPhone: {data['phone']}\n"
        f"Comment: {message.text[:1000]}\nTelegram: @{user.username or '-'} (id {user.id})"
    )
    for admin_id in admin_ids():
        await bot.send_message(admin_id, text, parse_mode=None)
    await message.answer(CONFIG["texts"]["done"], reply_markup=menu_kb())


def admin_ids() -> list[int]:
    return [int(x) for x in re.findall(r"\d+", os.getenv("ADMIN_IDS", ""))]


async def main() -> None:
    load_dotenv(Path(__file__).with_name(".env"))
    logging.basicConfig(level=logging.INFO)
    bot = Bot(os.environ["BOT_TOKEN"], default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
