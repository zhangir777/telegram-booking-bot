"""Client side: start, menu, booking flow, my bookings, info screens."""

from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from bot.config import settings
from bot.db.models import Booking, Master, Service, User
from bot.db.session import Session
from bot.i18n import booking_details, t
from bot.keyboards import builders as kb
from bot.keyboards.callbacks import (
    BookingCb,
    ConfirmCb,
    DayCb,
    LangCb,
    MasterCb,
    MenuCb,
    ServiceCb,
    TimeCb,
)
from bot.services import booking as svc
from bot.services.notify import notify_admins

router = Router(name="client")


class BookingFlow(StatesGroup):
    phone = State()


def now() -> datetime:
    return datetime.now(settings.tz).replace(tzinfo=None)


async def show_menu(target: Message | CallbackQuery, lang: str, text: str | None = None):
    text = text or t(lang, "menu")
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb.main_menu(lang))
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb.main_menu(lang))


# ---------- start, language, menu ----------


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(t("ru", "choose_lang"), reply_markup=kb.lang_kb())


@router.message(Command("menu"))
async def menu_cmd(message: Message, state: FSMContext, lang: str):
    await state.clear()
    await show_menu(message, lang)


@router.callback_query(LangCb.filter())
async def set_lang(call: CallbackQuery, callback_data: LangCb, user: User):
    async with Session() as s:
        db_user = await s.get(User, user.id)
        db_user.lang = callback_data.code
        await s.commit()
    lang = callback_data.code
    business = settings.business()["name"]
    await show_menu(
        call, lang, t(lang, "welcome", name=call.from_user.first_name, business=business)
    )


@router.callback_query(MenuCb.filter(F.action == "home"))
async def home(call: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    await show_menu(call, lang)


@router.callback_query(MenuCb.filter(F.action == "lang"))
async def choose_lang(call: CallbackQuery):
    await call.message.edit_text(t("ru", "choose_lang"), reply_markup=kb.lang_kb())
    await call.answer()


@router.callback_query(MenuCb.filter(F.action == "prices"))
async def prices(call: CallbackQuery, lang: str):
    async with Session() as s:
        services = await svc.active_services(s)
    lines = [
        t(
            lang,
            "price_line",
            name=x.name,
            price=f"{x.price:,}".replace(",", " "),
            duration=x.duration_min,
        )
        for x in services
    ]
    await call.message.edit_text(
        "\n".join([t(lang, "prices_title"), *lines]), reply_markup=kb.back_kb(lang)
    )
    await call.answer()


@router.callback_query(MenuCb.filter(F.action == "contacts"))
async def contacts(call: CallbackQuery, lang: str):
    b = settings.business()
    text = t(
        lang, "contacts", business=b["name"], address=b["address"][lang], phone=b["phone"],
        hours=b["hours"][lang],
    )  # fmt: skip
    await call.message.answer_location(b["location"]["lat"], b["location"]["lon"])
    await call.message.answer(text, reply_markup=kb.back_kb(lang))
    await call.answer()


@router.callback_query(MenuCb.filter(F.action == "faq"))
async def faq(call: CallbackQuery, lang: str):
    items = settings.business()["faq"][lang]
    text = "\n\n".join([t(lang, "faq_title"), *[f"<b>{q}</b>\n{a}" for q, a in items]])
    await call.message.edit_text(text, reply_markup=kb.back_kb(lang))
    await call.answer()


# ---------- booking flow: service -> master -> date -> time -> confirm ----------


@router.callback_query(MenuCb.filter(F.action == "book"))
async def book_start(call: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    async with Session() as s:
        services = await svc.active_services(s)
    await call.message.edit_text(
        t(lang, "choose_service"), reply_markup=kb.services_kb(lang, services)
    )
    await call.answer()


@router.callback_query(ServiceCb.filter())
async def pick_service(call: CallbackQuery, callback_data: ServiceCb, state: FSMContext, lang: str):
    async with Session() as s:
        service = await s.get(Service, callback_data.service_id)
        masters = await svc.active_masters(s)
    if not service or not service.active:
        return await call.answer(t(lang, "not_found"), show_alert=True)
    await state.update_data(service_id=service.id, move_id=None)
    await call.message.edit_text(
        t(lang, "choose_master"), reply_markup=kb.masters_kb(lang, masters)
    )
    await call.answer()


async def open_days(
    service_id: int, master_id: int | None, exclude: int | None = None
) -> set[date]:
    today = now().date()
    days = set()
    async with Session() as s:
        service = await s.get(Service, service_id)
        for i in range(settings.booking_days_ahead):
            d = today + timedelta(days=i)
            if await svc.available_slots(
                s, service, master_id, d, now(), settings.slot_step_minutes, exclude
            ):
                days.add(d)
    return days


async def show_calendar(call: CallbackQuery, state: FSMContext, lang: str, text_key="choose_date"):
    data = await state.get_data()
    days = await open_days(data["service_id"], data.get("master_id") or None, data.get("move_id"))
    await call.message.edit_text(
        t(lang, text_key),
        reply_markup=kb.calendar_kb(lang, now().date(), settings.booking_days_ahead, days),
    )
    await call.answer()


@router.callback_query(MasterCb.filter())
async def pick_master(call: CallbackQuery, callback_data: MasterCb, state: FSMContext, lang: str):
    data = await state.get_data()
    if "service_id" not in data:
        return await home(call, state, lang)
    if callback_data.master_id:
        async with Session() as s:
            master = await s.get(Master, callback_data.master_id)
        if not master or not master.active:
            return await call.answer(t(lang, "not_found"), show_alert=True)
    await state.update_data(master_id=callback_data.master_id)
    await show_calendar(call, state, lang)


@router.callback_query(MenuCb.filter(F.action == "dates"))
async def back_to_dates(call: CallbackQuery, state: FSMContext, lang: str):
    if "service_id" not in await state.get_data():
        return await home(call, state, lang)
    await show_calendar(call, state, lang)


@router.callback_query(DayCb.filter())
async def pick_day(call: CallbackQuery, callback_data: DayCb, state: FSMContext, lang: str):
    data = await state.get_data()
    try:
        day = datetime.strptime(callback_data.day, "%Y%m%d").date()
    except ValueError:
        return await call.answer()
    if "service_id" not in data or not 0 <= (day - now().date()).days < settings.booking_days_ahead:
        return await home(call, state, lang)
    async with Session() as s:
        service = await s.get(Service, data["service_id"])
        slots = await svc.available_slots(
            s, service, data.get("master_id") or None, day, now(), settings.slot_step_minutes,
            data.get("move_id"),
        )  # fmt: skip
    if not slots:
        return await call.answer(t(lang, "no_slots"), show_alert=True)
    await state.update_data(day=callback_data.day)
    await call.message.edit_text(
        t(lang, "choose_time", date=f"{day:%d.%m.%Y}"), reply_markup=kb.times_kb(lang, list(slots))
    )
    await call.answer()


@router.callback_query(TimeCb.filter())
async def pick_time(
    call: CallbackQuery, callback_data: TimeCb, state: FSMContext, lang: str, bot: Bot
):
    data = await state.get_data()
    if "day" not in data:
        return await home(call, state, lang)
    try:
        start = datetime.strptime(data["day"] + callback_data.hhmm, "%Y%m%d%H%M")
    except ValueError:
        return await call.answer()
    async with Session() as s:
        service = await s.get(Service, data["service_id"])
        slots = await svc.available_slots(
            s, service, data.get("master_id") or None, start.date(), now(), 5, data.get("move_id")
        )
        if start not in slots:
            return await call.answer(t(lang, "slot_taken"), show_alert=True)
        master = await s.get(Master, slots[start])
    await state.update_data(start=start.isoformat(), chosen_master=master.id)

    if data.get("move_id"):
        return await finish_reschedule(call, state, lang, bot)
    preview = Booking(start=start, service=service, master=master)
    await call.message.edit_text(
        t(lang, "confirm", details=booking_details(lang, preview)), reply_markup=kb.confirm_kb(lang)
    )
    await call.answer()


@router.callback_query(ConfirmCb.filter())
async def confirm(call: CallbackQuery, state: FSMContext, lang: str, user: User, bot: Bot):
    if "start" not in await state.get_data():
        return await home(call, state, lang)
    await call.answer()
    if not user.phone:
        await state.set_state(BookingFlow.phone)
        await call.message.answer(t(lang, "ask_phone"), reply_markup=kb.phone_kb(lang))
        return
    await finish_booking(call.message, state, lang, user.id, bot)


@router.message(BookingFlow.phone, F.contact)
async def got_phone(message: Message, state: FSMContext, lang: str, bot: Bot):
    if message.contact.user_id != message.from_user.id:
        return await message.answer(t(lang, "ask_phone"), reply_markup=kb.phone_kb(lang))
    async with Session() as s:
        db_user = await s.get(User, message.from_user.id)
        db_user.phone = message.contact.phone_number
        await s.commit()
    await message.answer("✅", reply_markup=ReplyKeyboardRemove())
    await finish_booking(message, state, lang, message.from_user.id, bot)


@router.message(BookingFlow.phone)
async def phone_expected(message: Message, lang: str):
    await message.answer(t(lang, "ask_phone"), reply_markup=kb.phone_kb(lang))


async def load_booking(booking_id: int) -> Booking | None:
    async with Session() as s:
        return await s.get(Booking, booking_id)


async def finish_booking(message: Message, state: FSMContext, lang: str, user_id: int, bot: Bot):
    data = await state.get_data()
    await state.clear()
    try:
        b = await svc.create_booking(
            Session, user_id, data["chosen_master"], data["service_id"],
            datetime.fromisoformat(data["start"]), now(),
        )  # fmt: skip
    except svc.SlotTaken:
        return await message.answer(t(lang, "slot_taken"), reply_markup=kb.main_menu(lang))
    b = await load_booking(b.id)
    await message.answer(
        t(lang, "booked", details=booking_details(lang, b)), reply_markup=kb.main_menu(lang)
    )
    client = f"Client: {b.user.name} {b.user.phone or ''}"
    await notify_admins(
        bot, settings.admin_ids, f"🆕 New booking #{b.id}\n{booking_details('en', b)}\n{client}"
    )


async def finish_reschedule(call: CallbackQuery, state: FSMContext, lang: str, bot: Bot):
    data = await state.get_data()
    await state.clear()
    try:
        b = await svc.reschedule_booking(
            Session,
            data["move_id"],
            call.from_user.id,
            datetime.fromisoformat(data["start"]),
            now(),
        )
    except svc.SlotTaken:
        return await call.answer(t(lang, "slot_taken"), show_alert=True)
    except LookupError:
        return await call.answer(t(lang, "not_found"), show_alert=True)
    b = await load_booking(b.id)
    await call.message.edit_text(
        t(lang, "rescheduled", details=booking_details(lang, b)), reply_markup=kb.main_menu(lang)
    )
    await call.answer()
    await notify_admins(
        bot, settings.admin_ids, f"🔁 Rescheduled #{b.id}\n{booking_details('en', b)}"
    )


# ---------- my bookings ----------


@router.callback_query(MenuCb.filter(F.action == "my"))
async def my_bookings(call: CallbackQuery, lang: str):
    async with Session() as s:
        items = await svc.user_bookings(s, call.from_user.id, now())
    await call.answer()
    if not items:
        return await call.message.edit_text(t(lang, "my_empty"), reply_markup=kb.back_kb(lang))
    await call.message.edit_text(t(lang, "my_list"))
    for b in items:
        await call.message.answer(
            booking_details(lang, b), reply_markup=kb.booking_actions_kb(lang, b.id)
        )
    await call.message.answer(t(lang, "menu"), reply_markup=kb.main_menu(lang))


@router.callback_query(BookingCb.filter(F.action == "cancel"))
async def cancel(call: CallbackQuery, callback_data: BookingCb, lang: str, bot: Bot):
    try:
        b = await svc.cancel_booking(Session, callback_data.booking_id, call.from_user.id)
    except LookupError:
        return await call.answer(t(lang, "not_found"), show_alert=True)
    b = await load_booking(b.id)
    await call.message.edit_text(f"{t(lang, 'cancelled')}\n\n{booking_details(lang, b)}")
    await call.answer()
    await notify_admins(
        bot, settings.admin_ids, f"❌ Cancelled #{b.id}\n{booking_details('en', b)}"
    )


@router.callback_query(BookingCb.filter(F.action == "move"))
async def move(call: CallbackQuery, callback_data: BookingCb, state: FSMContext, lang: str):
    b = await load_booking(callback_data.booking_id)
    if not b or b.user_id != call.from_user.id or b.status != "active":
        return await call.answer(t(lang, "not_found"), show_alert=True)
    await state.set_data({"service_id": b.service_id, "master_id": b.master_id, "move_id": b.id})
    await show_calendar(call, state, lang, "reschedule_pick")


@router.callback_query(BookingCb.filter(F.action == "visit_ok"))
async def visit_ok(call: CallbackQuery, callback_data: BookingCb, lang: str):
    async with Session() as s:
        b = await s.get(Booking, callback_data.booking_id)
        if not b or b.user_id != call.from_user.id or b.status != "active":
            return await call.answer(t(lang, "not_found"), show_alert=True)
        b.confirmed = True
        await s.commit()
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer(t(lang, "visit_confirmed"), show_alert=True)


# ---------- privacy ----------


@router.message(Command("deletemydata"))
async def delete_my_data(message: Message, state: FSMContext, lang: str):
    await state.clear()
    await svc.delete_user_data(Session, message.from_user.id)
    await message.answer(t(lang, "privacy_deleted"), reply_markup=ReplyKeyboardRemove())
