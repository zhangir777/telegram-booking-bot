from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.db.models import Master, Service, User
from bot.db.session import init_db, make_engine

NOW = datetime(2026, 11, 2, 9, 0)  # Monday 09:00 Almaty
SCHEDULE = {str(d): ["10:00", "18:00"] for d in range(5)}


@pytest.fixture
async def sm(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    await init_db(engine)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s, s.begin():
        s.add_all(
            [
                Master(id=1, name="A", schedule=SCHEDULE, break_start="13:00", break_end="14:00"),
                Master(id=2, name="B", schedule=SCHEDULE),
                Service(id=1, name="Cut", price=5000, duration_min=60),
                User(id=10, name="u10"),
                User(id=11, name="u11"),
            ]
        )
    yield maker
    await engine.dispose()
