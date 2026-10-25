"""Tables. Times are naive datetimes in the business timezone (settings.timezone)."""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, ForeignKey, Index, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user id
    name: Mapped[str] = mapped_column(String(128), default="")
    phone: Mapped[str | None] = mapped_column(String(32))
    lang: Mapped[str] = mapped_column(String(2), default="ru")
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class Master(Base):
    __tablename__ = "masters"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    # {"0": ["10:00", "19:00"], ...} weekday (Mon=0) -> work hours; missing day = day off
    schedule: Mapped[dict] = mapped_column(JSON, default=dict)
    break_start: Mapped[str | None] = mapped_column(String(5))  # "13:00"
    break_end: Mapped[str | None] = mapped_column(String(5))
    active: Mapped[bool] = mapped_column(default=True)


class Service(Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    price: Mapped[int]  # tenge
    duration_min: Mapped[int]
    active: Mapped[bool] = mapped_column(default=True)


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id"))
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    start: Mapped[datetime]
    end: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / cancelled
    confirmed: Mapped[bool] = mapped_column(default=False)
    reminded_24h: Mapped[bool] = mapped_column(default=False)
    reminded_2h: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    user: Mapped[User] = relationship(lazy="joined")
    master: Mapped[Master] = relationship(lazy="joined")
    service: Mapped[Service] = relationship(lazy="joined")

    __table_args__ = (
        # DB-level guard: one active booking per master per start time
        Index(
            "uq_active_master_start",
            "master_id",
            "start",
            unique=True,
            sqlite_where=text("status = 'active'"),
        ),
    )


class BlockedSlot(Base):
    """Closed time: day off, lunch, holiday. master_id None = whole business."""

    __tablename__ = "blocked_slots"
    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int | None] = mapped_column(ForeignKey("masters.id"))
    start: Mapped[datetime]
    end: Mapped[datetime]
    reason: Mapped[str] = mapped_column(String(64), default="")
