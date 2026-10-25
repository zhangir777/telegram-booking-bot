from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from bot.config import settings

from .models import Base


def make_engine(url: str = settings.database_url) -> AsyncEngine:
    if url.startswith("sqlite") and ":///" in url and ":memory:" not in url:
        Path(url.split(":///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(url, connect_args={"timeout": 30})

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


async def init_db(engine: AsyncEngine) -> None:
    """Simple migration strategy: create missing tables (no destructive changes)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


engine = make_engine()
Session = async_sessionmaker(engine, expire_on_commit=False)
