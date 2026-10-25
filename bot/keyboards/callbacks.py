"""Typed callback data. aiogram parses and validates the types; handlers re-check ownership."""

from aiogram.filters.callback_data import CallbackData


class LangCb(CallbackData, prefix="lang"):
    code: str


class MenuCb(CallbackData, prefix="menu"):
    action: str


class ServiceCb(CallbackData, prefix="svc"):
    service_id: int


class MasterCb(CallbackData, prefix="mst"):
    master_id: int  # 0 = any


class DayCb(CallbackData, prefix="day"):
    day: str  # YYYYMMDD


class TimeCb(CallbackData, prefix="tm"):
    hhmm: str  # HHMM


class ConfirmCb(CallbackData, prefix="ok"):
    pass


class BookingCb(CallbackData, prefix="bk"):
    action: str  # cancel / move / visit_ok
    booking_id: int


class AdminCb(CallbackData, prefix="adm"):
    action: str
    arg: str = ""
