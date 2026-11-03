from datetime import datetime, time
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Role(StrEnum):
    client = "client"
    master = "master"
    admin = "admin"


class AppointmentStatus(StrEnum):
    booked = "booked"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"


class AppointmentSource(StrEnum):
    web = "web"
    chat = "chat"
    admin = "admin"


def _enum(enum_cls):
    return Enum(enum_cls, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e])


master_services = Table(
    "master_services",
    Base.metadata,
    Column("master_id", ForeignKey("masters.id", ondelete="CASCADE"), primary_key=True),
    Column("service_id", ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(30))
    role: Mapped[Role] = mapped_column(_enum(Role), default=Role.client)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    master: Mapped["Master | None"] = relationship(back_populates="user", uselist=False)


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    # {"tk": ..., "ru": ..., "en": ...}
    name: Mapped[dict] = mapped_column(JSONB)
    description: Mapped[dict] = mapped_column(JSONB, default=dict)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (CheckConstraint("duration_minutes > 0"), CheckConstraint("price >= 0"))


class Master(Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    title: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(default=True)

    user: Mapped[User] = relationship(back_populates="master")
    services: Mapped[list[Service]] = relationship(secondary=master_services)
    hours: Mapped[list["WorkingHours"]] = relationship(
        cascade="all, delete-orphan", order_by="WorkingHours.weekday"
    )


class WorkingHours(Base):
    __tablename__ = "working_hours"

    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id", ondelete="CASCADE"))
    # 0 = понедельник ... 6 = воскресенье
    weekday: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    __table_args__ = (
        UniqueConstraint("master_id", "weekday"),
        CheckConstraint("weekday BETWEEN 0 AND 6"),
        CheckConstraint("start_time < end_time"),
    )


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Цена на момент записи: последующее изменение прайса не меняет историю
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    status: Mapped[AppointmentStatus] = mapped_column(
        _enum(AppointmentStatus), default=AppointmentStatus.booked, index=True
    )
    source: Mapped[AppointmentSource] = mapped_column(_enum(AppointmentSource), default=AppointmentSource.web)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped[User] = relationship()
    master: Mapped[Master] = relationship()
    service: Mapped[Service] = relationship()

    __table_args__ = (
        CheckConstraint("starts_at < ends_at"),
        # Защита от двойной записи на уровне БД: работает и при одновременных запросах
        ExcludeConstraint(
            ("master_id", "="),
            (text("tstzrange(starts_at, ends_at)"), "&&"),
            where=text("status IN ('booked', 'completed')"),
            using="gist",
            name="no_master_overlap",
        ),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # История в формате Messages API. Только дополняется, старые сообщения не редактируются.
    messages: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NailAnalysis(Base):
    __tablename__ = "nail_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Сохраняется только результат: сами фотографии на сервере не хранятся
    result: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
