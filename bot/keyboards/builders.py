from datetime import date, datetime, timedelta

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.i18n import LANGS, money, t, title

from .callbacks import (
    BookingCb,
    ConfirmCb,
    DayCb,
    LangCb,
    MasterCb,
    MenuCb,
    ServiceCb,
    TimeCb,
)

LANG_NAMES = {"ru": "🇷🇺 Русский", "kk": "🇰🇿 Қазақша", "en": "🇬🇧 English"}
WEEKDAYS = {
    "ru": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
    "kk": ["Дс", "Сс", "Ср", "Бс", "Жм", "Сб", "Жс"],
    "en": ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
}


def lang_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for code in LANGS:
        kb.button(text=LANG_NAMES[code], callback_data=LangCb(code=code))
    return kb.adjust(3).as_markup()


def main_menu(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for action in ("book", "my", "prices", "contacts", "faq", "lang"):
        kb.button(text=t(lang, f"btn_{action}"), callback_data=MenuCb(action=action))
    return kb.adjust(1, 1, 2, 2).as_markup()


def back_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_back"), callback_data=MenuCb(action="home"))
    return kb.as_markup()


def services_kb(lang: str, services) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in services:
        kb.button(
            text=f"{title(s, lang)} · {money(lang, s.price)}",
            callback_data=ServiceCb(service_id=s.id),
        )
    kb.button(text=t(lang, "btn_back"), callback_data=MenuCb(action="home"))
    return kb.adjust(1).as_markup()


def masters_kb(lang: str, masters) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "any_master"), callback_data=MasterCb(master_id=0))
    for m in masters:
        kb.button(text=title(m, lang), callback_data=MasterCb(master_id=m.id))
    kb.button(text=t(lang, "btn_back"), callback_data=MenuCb(action="book"))
    return kb.adjust(1).as_markup()


def calendar_kb(lang: str, today: date, days: int, open_days: set[date]) -> InlineKeyboardMarkup:
    """Next `days` days, 4 per row; days without free time are not shown."""
    kb = InlineKeyboardBuilder()
    for i in range(days):
        d = today + timedelta(days=i)
        if d in open_days:
            label = f"{WEEKDAYS.get(lang, WEEKDAYS['ru'])[d.weekday()]} {d:%d.%m}"
            kb.button(text=label, callback_data=DayCb(day=f"{d:%Y%m%d}"))
    kb.adjust(4)
    back = InlineKeyboardBuilder()
    back.button(text=t(lang, "btn_back"), callback_data=MenuCb(action="home"))
    kb.attach(back)
    return kb.as_markup()


def times_kb(lang: str, slots: list[datetime]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in slots:
        kb.button(text=f"{s:%H:%M}", callback_data=TimeCb(hhmm=f"{s:%H%M}"))
    kb.adjust(4)
    back = InlineKeyboardBuilder()
    back.button(text=t(lang, "btn_back"), callback_data=MenuCb(action="dates"))
    kb.attach(back)
    return kb.as_markup()


def confirm_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_confirm"), callback_data=ConfirmCb())
    kb.button(text=t(lang, "btn_cancel"), callback_data=MenuCb(action="home"))
    return kb.adjust(2).as_markup()


def phone_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "btn_share_phone"), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def booking_actions_kb(lang: str, booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=t(lang, "btn_reschedule"),
        callback_data=BookingCb(action="move", booking_id=booking_id),
    )
    kb.button(
        text=t(lang, "btn_cancel_booking"),
        callback_data=BookingCb(action="cancel", booking_id=booking_id),
    )
    return kb.adjust(2).as_markup()


def reminder_kb(lang: str, booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=t(lang, "btn_i_confirm"),
        callback_data=BookingCb(action="visit_ok", booking_id=booking_id),
    )
    kb.button(
        text=t(lang, "btn_cancel_booking"),
        callback_data=BookingCb(action="cancel", booking_id=booking_id),
    )
    return kb.adjust(2).as_markup()
