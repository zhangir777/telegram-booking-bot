"""Admin side. The router has AdminOnlyMiddleware, so non-admins never reach these handlers."""

from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from bot.db.models import Service, User
from bot.db.session import Session
from bot.handlers.client.booking import now
from bot.keyboards.callbacks import AdminCb
from bot.services import booking as svc
from bot.services.export import to_csv, to_xlsx
from bot.services.notify import broadcast

router = Router(name="admin")

HELP = """<b>Admin panel</b>
/day 2026-11-03 — bookings on a date
/close 2026-11-03 — close the whole day
/close 2026-11-03 13:00-14:00 [master_id] — close a time slot
/services — list services with IDs
/addservice Name;price;minutes — add a service
/setprice ID price — change price
/hideservice ID — hide a service
/export 2026-11-01 2026-11-30 — Excel + CSV for a period
/broadcast text — message to all clients (asks to confirm)"""


class BroadcastFlow(StatesGroup):
    confirm = State()


def admin_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Today", callback_data=AdminCb(action="today"))
    kb.button(text="📋 Tomorrow", callback_data=AdminCb(action="tomorrow"))
    kb.button(text="📊 Export this month", callback_data=AdminCb(action="export_month"))
    kb.button(text="💰 Services", callback_data=AdminCb(action="services"))
    return kb.adjust(2).as_markup()


def parse_day(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


async def day_report(day: date) -> str:
    start = datetime.combine(day, datetime.min.time())
    async with Session() as s:
        items = await svc.bookings_between(s, start, start + timedelta(days=1))
    if not items:
        return f"{day:%d.%m.%Y}: no bookings"
    lines = [
        f"{b.start:%H:%M}–{b.end:%H:%M} {b.master.name}: {b.service.name}, "
        f"{b.user.name} {b.user.phone or ''}{' ✅' if b.confirmed else ''}"
        for b in items
    ]
    return f"<b>{day:%d.%m.%Y}</b> ({len(items)})\n" + "\n".join(lines)


@router.message(Command("admin"))
async def admin_home(message: Message):
    await message.answer(HELP, reply_markup=admin_kb())


@router.callback_query(AdminCb.filter(F.action.in_({"today", "tomorrow"})))
async def quick_day(call: CallbackQuery, callback_data: AdminCb):
    day = now().date() + timedelta(days=1 if callback_data.action == "tomorrow" else 0)
    await call.message.answer(await day_report(day))
    await call.answer()


@router.message(Command("day"))
async def day_cmd(message: Message, command: CommandObject):
    day = parse_day(command.args or "")
    if not day:
        return await message.answer("Usage: /day 2026-11-03")
    await message.answer(await day_report(day))


@router.message(Command("close"))
async def close_cmd(message: Message, command: CommandObject):
    parts = (command.args or "").split()
    day = parse_day(parts[0]) if parts else None
    if not day:
        return await message.answer("Usage: /close 2026-11-03 [13:00-14:00] [master_id]")
    start, end = datetime.combine(day, datetime.min.time()), None
    master_id = None
    try:
        if len(parts) > 1:
            a, b = parts[1].split("-")
            start = datetime.combine(day, datetime.strptime(a, "%H:%M").time())
            end = datetime.combine(day, datetime.strptime(b, "%H:%M").time())
        if len(parts) > 2:
            master_id = int(parts[2])
    except ValueError:
        return await message.answer("Wrong time format. Example: /close 2026-11-03 13:00-14:00 2")
    end = end or start + timedelta(days=1)
    if end <= start:
        return await message.answer("End must be after start")
    await svc.block_time(Session, master_id, start, end, "closed by admin")
    async with Session() as s:
        clash = svc.conflicts(await svc.bookings_between(s, start, end), start, end)
    clash = [b for b in clash if master_id in (None, b.master_id)]
    text = f"Closed {start:%d.%m %H:%M}–{end:%d.%m %H:%M}" + (
        f" for master {master_id}" if master_id else ""
    )
    if clash:
        text += "\n⚠️ Existing bookings in this time (contact clients): " + ", ".join(
            f"#{b.id}" for b in clash
        )
    await message.answer(text)


async def services_text() -> str:
    async with Session() as s:
        items = list(await s.scalars(select(Service).order_by(Service.id)))
    return (
        "\n".join(
            f"{x.id}. {x.name} — {x.price} ₸, {x.duration_min} min{'' if x.active else ' (hidden)'}"
            for x in items
        )
        or "No services"
    )


@router.message(Command("services"))
async def services_cmd(message: Message):
    await message.answer(await services_text())


@router.callback_query(AdminCb.filter(F.action == "services"))
async def services_cb(call: CallbackQuery):
    await call.message.answer(await services_text())
    await call.answer()


@router.message(Command("addservice"))
async def add_service(message: Message, command: CommandObject):
    try:
        name, price, minutes = (p.strip() for p in (command.args or "").split(";"))
        service = Service(name=name, price=int(price), duration_min=int(minutes))
        if not name or service.price < 0 or not 5 <= service.duration_min <= 600:
            raise ValueError
    except ValueError:
        return await message.answer("Usage: /addservice Haircut;5000;60")
    async with Session() as s:
        s.add(service)
        await s.commit()
    await message.answer(f"Added #{service.id}: {service.name}")


@router.message(Command("setprice", "hideservice"))
async def edit_service(message: Message, command: CommandObject):
    parts = (command.args or "").split()
    try:
        service_id = int(parts[0])
        price = int(parts[1]) if command.command == "setprice" else None
    except (ValueError, IndexError):
        return await message.answer("Usage: /setprice 3 7000 or /hideservice 3")
    async with Session() as s:
        service = await s.get(Service, service_id)
        if not service:
            return await message.answer("Service not found")
        if price is None:
            service.active = False
        else:
            service.price = price
        await s.commit()
    await message.answer("Saved.\n" + await services_text())


async def send_export(message: Message, start: date, end: date):
    async with Session() as s:
        items = await svc.bookings_between(
            s, datetime.combine(start, datetime.min.time()),
            datetime.combine(end + timedelta(days=1), datetime.min.time()), only_active=False,
        )  # fmt: skip
    name = f"bookings_{start}_{end}"
    await message.answer_document(
        BufferedInputFile(to_xlsx(items), f"{name}.xlsx"), caption=f"{len(items)} bookings"
    )
    await message.answer_document(BufferedInputFile(to_csv(items), f"{name}.csv"))


@router.message(Command("export"))
async def export_cmd(message: Message, command: CommandObject):
    parts = (command.args or "").split()
    days = [parse_day(p) for p in parts[:2]]
    if len(days) != 2 or None in days or days[0] > days[1]:
        return await message.answer("Usage: /export 2026-11-01 2026-11-30")
    await send_export(message, days[0], days[1])


@router.callback_query(AdminCb.filter(F.action == "export_month"))
async def export_month(call: CallbackQuery):
    today = now().date()
    await call.answer()
    await send_export(call.message, today.replace(day=1), today)


@router.message(Command("broadcast"))
async def broadcast_start(message: Message, command: CommandObject, state: FSMContext):
    if not command.args:
        return await message.answer("Usage: /broadcast Your text")
    async with Session() as s:
        count = len(list(await s.scalars(select(User.id))))
    await state.set_state(BroadcastFlow.confirm)
    await state.update_data(text=command.args)
    kb = InlineKeyboardBuilder()
    kb.button(text=f"✅ Send to {count}", callback_data=AdminCb(action="bc_send"))
    kb.button(text="Cancel", callback_data=AdminCb(action="bc_cancel"))
    await message.answer(f"Preview:\n\n{command.args}", reply_markup=kb.as_markup())


@router.callback_query(
    BroadcastFlow.confirm, AdminCb.filter(F.action.in_({"bc_send", "bc_cancel"}))
)
async def broadcast_go(call: CallbackQuery, callback_data: AdminCb, state: FSMContext, bot: Bot):
    text = (await state.get_data())["text"]
    await state.clear()
    await call.message.edit_reply_markup(reply_markup=None)
    if callback_data.action == "bc_cancel":
        return await call.answer("Cancelled")
    await call.answer("Sending…")
    async with Session() as s:
        ids = list(await s.scalars(select(User.id)))
    sent, failed = await broadcast(lambda uid: bot.send_message(uid, text), ids)
    await call.message.answer(f"Broadcast done: {sent} sent, {failed} failed")
