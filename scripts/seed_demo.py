"""Fill the DB with the fictional "Demo Beauty Almaty". All data is made up.

uv run seed-demo
"""

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import delete

from bot.config import settings
from bot.db.models import BlockedSlot, Booking, Master, Service, User
from bot.db.session import Session, engine, init_db
from bot.services.booking import available_slots

WEEK = {str(d): ["10:00", "20:00"] for d in range(6)}  # Mon-Sat

MASTERS = [
    Master(name="Айгерим", schedule=WEEK, break_start="14:00", break_end="15:00"),
    Master(name="Дана", schedule={str(d): ["11:00", "20:00"] for d in (1, 2, 3, 4, 5)}),
    Master(name="Арман (барбер)", schedule=WEEK, break_start="13:00", break_end="14:00"),
]
SERVICES = [
    Service(name="Женская стрижка", price=8000, duration_min=60),
    Service(name="Мужская стрижка", price=5000, duration_min=45),
    Service(name="Окрашивание", price=20000, duration_min=120),
    Service(name="Маникюр", price=6000, duration_min=60),
    Service(name="Укладка", price=7000, duration_min=45),
    Service(name="Борода", price=3000, duration_min=30),
]
CLIENTS = [
    User(id=1001, name="Demo Client 1", phone="+77000000001", lang="ru"),
    User(id=1002, name="Demo Client 2", phone="+77000000002", lang="kk"),
    User(id=1003, name="Demo Client 3", phone="+77000000003", lang="en"),
]


async def seed() -> None:
    await init_db(engine)
    async with Session() as s, s.begin():
        for model in (Booking, BlockedSlot, Service, Master):
            await s.execute(delete(model))
        await s.execute(delete(User).where(User.id.in_([c.id for c in CLIENTS])))
        s.add_all(MASTERS + SERVICES + CLIENTS)

    now = datetime.now(settings.tz).replace(tzinfo=None)
    async with Session() as s, s.begin():
        made = 0
        for i, client in enumerate(CLIENTS * 2):
            service = SERVICES[i % len(SERVICES)]
            day = (now + timedelta(days=1 + i)).date()
            slots = await available_slots(s, service, None, day, now)
            if slots:
                start, master_id = list(slots.items())[len(slots) // 2]
                s.add(
                    Booking(
                        user_id=client.id, master_id=master_id, service_id=service.id,
                        start=start, end=start + timedelta(minutes=service.duration_min),
                        created_at=now,
                    )
                )  # fmt: skip
                await s.flush()
                made += 1
    print(f"Seeded: {len(MASTERS)} masters, {len(SERVICES)} services, {made} demo bookings")


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
