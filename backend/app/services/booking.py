"""Расчёт свободных окон и создание записи. Этим кодом пользуются и REST API, и чат-ассистент."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import Appointment, AppointmentSource, AppointmentStatus, Master, Service

ACTIVE_STATUSES = (AppointmentStatus.booked, AppointmentStatus.completed)


class BookingError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class Slot:
    master_id: int
    master_name: str
    starts_at: datetime


def _masters_for(db: Session, service_id: int, master_id: int | None = None) -> list[Master]:
    query = (
        select(Master)
        .where(Master.is_active, Master.services.any(Service.id == service_id))
        .options(selectinload(Master.hours), selectinload(Master.user))
        .order_by(Master.id)
    )
    if master_id is not None:
        query = query.where(Master.id == master_id)
    return list(db.scalars(query))


def _busy_intervals(db: Session, master_ids: list[int], start: datetime, end: datetime):
    rows = db.execute(
        select(Appointment.master_id, Appointment.starts_at, Appointment.ends_at).where(
            Appointment.master_id.in_(master_ids),
            Appointment.status.in_(ACTIVE_STATUSES),
            Appointment.starts_at < end,
            Appointment.ends_at > start,
        )
    )
    busy: dict[int, list[tuple[datetime, datetime]]] = {}
    for master_id, starts_at, ends_at in rows:
        busy.setdefault(master_id, []).append((starts_at, ends_at))
    return busy


def available_slots(
    db: Session,
    service: Service,
    on_date: date,
    master_id: int | None = None,
    now: datetime | None = None,
) -> list[Slot]:
    now = now or datetime.now(UTC)
    masters = _masters_for(db, service.id, master_id)
    if not masters:
        return []

    day_start = datetime.combine(on_date, datetime.min.time(), tzinfo=settings.tz)
    busy = _busy_intervals(db, [m.id for m in masters], day_start, day_start + timedelta(days=1))
    duration = timedelta(minutes=service.duration_minutes)
    step = timedelta(minutes=settings.slot_minutes)

    slots: list[Slot] = []
    for master in masters:
        hours = next((h for h in master.hours if h.weekday == on_date.weekday()), None)
        if hours is None:
            continue
        current = datetime.combine(on_date, hours.start_time, tzinfo=settings.tz)
        closing = datetime.combine(on_date, hours.end_time, tzinfo=settings.tz)
        while current + duration <= closing:
            end = current + duration
            free = all(end <= s or current >= e for s, e in busy.get(master.id, []))
            if free and current > now:
                slots.append(Slot(master.id, master.user.full_name, current))
            current += step
    slots.sort(key=lambda s: (s.starts_at, s.master_id))
    return slots


def create_appointment(
    db: Session,
    client_id: int,
    service_id: int,
    master_id: int,
    starts_at: datetime,
    notes: str | None = None,
    source: AppointmentSource = AppointmentSource.web,
    now: datetime | None = None,
) -> Appointment:
    now = now or datetime.now(UTC)
    service = db.get(Service, service_id)
    if service is None or not service.is_active:
        raise BookingError("service_not_found")
    masters = _masters_for(db, service_id, master_id)
    if not masters:
        raise BookingError("master_cannot_do_service")
    if starts_at <= now:
        raise BookingError("slot_in_past")

    ends_at = starts_at + timedelta(minutes=service.duration_minutes)
    local_start = starts_at.astimezone(settings.tz)
    local_end = ends_at.astimezone(settings.tz)
    hours = next((h for h in masters[0].hours if h.weekday == local_start.weekday()), None)
    if (
        hours is None
        or local_start.date() != local_end.date()
        or local_start.time() < hours.start_time
        or local_end.time() > hours.end_time
    ):
        raise BookingError("outside_working_hours")

    appointment = Appointment(
        client_id=client_id,
        master_id=master_id,
        service_id=service_id,
        starts_at=starts_at,
        ends_at=ends_at,
        price=service.price,
        notes=notes,
        source=source,
    )
    db.add(appointment)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "no_master_overlap" in str(exc.orig):
            raise BookingError("slot_taken") from exc
        raise
    return appointment


def cancel_appointment(db: Session, appointment: Appointment, now: datetime | None = None) -> Appointment:
    now = now or datetime.now(UTC)
    if appointment.status != AppointmentStatus.booked:
        raise BookingError("cannot_cancel")
    if appointment.starts_at <= now:
        raise BookingError("cannot_cancel")
    appointment.status = AppointmentStatus.cancelled
    db.commit()
    return appointment
