from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import CurrentUser, Db, api_error
from app.models import Appointment, AppointmentSource, Master, Role, User
from app.schemas import AppointmentIn, AppointmentOut
from app.services import booking

router = APIRouter(prefix="/api/appointments", tags=["appointments"])

APPOINTMENT_LOAD = (
    selectinload(Appointment.client),
    selectinload(Appointment.service),
    selectinload(Appointment.master).selectinload(Master.user),
)

BOOKING_ERROR_STATUS = {
    "service_not_found": 404,
    "master_cannot_do_service": 422,
    "outside_working_hours": 422,
    "slot_in_past": 422,
    "slot_taken": 409,
    "cannot_cancel": 409,
}


def booking_http_error(error: booking.BookingError):
    return api_error(BOOKING_ERROR_STATUS[error.code], error.code)


def appointment_out(a: Appointment) -> AppointmentOut:
    return AppointmentOut(
        id=a.id,
        client_id=a.client_id,
        client_name=a.client.full_name,
        client_phone=a.client.phone,
        master_id=a.master_id,
        master_name=a.master.user.full_name,
        service_id=a.service_id,
        service_name=a.service.name,
        starts_at=a.starts_at,
        ends_at=a.ends_at,
        price=float(a.price),
        status=a.status,
        source=a.source,
        notes=a.notes,
    )


@router.get("/mine", response_model=list[AppointmentOut])
def my_appointments(db: Db, user: CurrentUser):
    rows = db.scalars(
        select(Appointment)
        .where(Appointment.client_id == user.id)
        .options(*APPOINTMENT_LOAD)
        .order_by(Appointment.starts_at.desc())
        .limit(100)
    )
    return [appointment_out(a) for a in rows]


@router.post("", response_model=AppointmentOut, status_code=201)
def create(body: AppointmentIn, db: Db, user: CurrentUser):
    client_id = user.id
    source = AppointmentSource.web
    if body.client_id is not None and body.client_id != user.id:
        if user.role != Role.admin:
            raise api_error(403, "forbidden")
        client = db.get(User, body.client_id)
        if client is None or client.role != Role.client:
            raise api_error(404, "client_not_found")
        client_id = client.id
        source = AppointmentSource.admin
    try:
        appointment = booking.create_appointment(
            db, client_id, body.service_id, body.master_id, body.starts_at, body.notes, source
        )
    except booking.BookingError as exc:
        raise booking_http_error(exc) from exc
    return appointment_out(appointment)


@router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel(appointment_id: int, db: Db, user: CurrentUser):
    appointment = db.get(Appointment, appointment_id, options=APPOINTMENT_LOAD)
    # Чужая запись выглядит как несуществующая: id не раскрывает данные других клиентов
    if appointment is None or (appointment.client_id != user.id and user.role != Role.admin):
        raise api_error(404, "appointment_not_found")
    try:
        booking.cancel_appointment(db, appointment)
    except booking.BookingError as exc:
        raise booking_http_error(exc) from exc
    return appointment_out(appointment)
