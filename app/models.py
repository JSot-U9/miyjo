from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .catalog import minutes_between
from .config import now
from .db import Base


def _csv(value: str) -> list[str]:
    return [x for x in (value or "").split(",") if x]


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(15), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80), default="")
    role: Mapped[str] = mapped_column(String(10), default="parent")  # parent | provider | admin
    consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    children: Mapped[list["Child"]] = relationship(back_populates="parent", cascade="all, delete-orphan")
    provider: Mapped["Provider | None"] = relationship(back_populates="user", uselist=False)


class Child(Base):
    """Datos mínimos del menor (sin apellidos ni fecha de nacimiento): minimización de datos."""
    __tablename__ = "children"
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    age: Mapped[int] = mapped_column(Integer)
    interests_csv: Mapped[str] = mapped_column(String(120), default="")
    days_csv: Mapped[str] = mapped_column(String(40), default="")
    slots_csv: Mapped[str] = mapped_column(String(40), default="")
    zone: Mapped[str] = mapped_column(String(40), default="")
    budget: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    parent: Mapped[User] = relationship(back_populates="children")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="child", cascade="all, delete-orphan")

    interests = property(lambda s: _csv(s.interests_csv))
    days = property(lambda s: _csv(s.days_csv))
    slots = property(lambda s: _csv(s.slots_csv))


class Provider(Base):
    __tablename__ = "providers"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20), default="academia")
    zone: Mapped[str] = mapped_column(String(40))
    address: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    yape: Mapped[str] = mapped_column(String(15), default="")
    checks_csv: Mapped[str] = mapped_column(Text, default="")  # items verificados, separados por "|"
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="provider")
    activities: Mapped[list["Activity"]] = relationship(back_populates="provider", cascade="all, delete-orphan")

    checks = property(lambda s: [x for x in (s.checks_csv or "").split("|") if x])


class Activity(Base):
    __tablename__ = "activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(20))
    min_age: Mapped[int] = mapped_column(Integer)
    max_age: Mapped[int] = mapped_column(Integer)
    days_csv: Mapped[str] = mapped_column(String(40))
    start: Mapped[str] = mapped_column(String(5))  # HH:MM
    end: Mapped[str] = mapped_column(String(5))
    price_month: Mapped[int] = mapped_column(Integer)
    trial_price: Mapped[int] = mapped_column(Integer, default=0)
    capacity: Mapped[int] = mapped_column(Integer, default=12)
    level: Mapped[str] = mapped_column(String(30), default="Todos los niveles")
    safety: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    provider: Mapped[Provider] = relationship(back_populates="activities")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="activity")

    days = property(lambda s: _csv(s.days_csv))
    session_minutes = property(lambda s: minutes_between(s.start, s.end))


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id"), index=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # prueba | mensual
    status: Mapped[str] = mapped_column(String(12), default="pendiente")  # pendiente | confirmada | cancelada
    amount: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    child: Mapped[Child] = relationship(back_populates="bookings")
    activity: Mapped[Activity] = relationship(back_populates="bookings")
    attendances: Mapped[list["Attendance"]] = relationship(back_populates="booking", cascade="all, delete-orphan")


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("booking_id", "day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    present: Mapped[bool] = mapped_column(Boolean, default=True)

    booking: Mapped[Booking] = relationship(back_populates="attendances")


class Event(Base):
    """Registro de eventos del embudo: base de las métricas para patrocinadores."""
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(30), index=True)
    data: Mapped[str] = mapped_column(String(200), default="")
    ts: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class Notification(Base):
    """Bandeja de salida de mensajes (WhatsApp/SMS). En demo se lee en /demo/mensajes."""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(15), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Otp(Base):
    __tablename__ = "otps"
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(15), index=True)
    code: Mapped[str] = mapped_column(String(6))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
