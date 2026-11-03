from datetime import date, datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.config import settings
from app.deps import AdminUser, Db, StaffUser, api_error
from app.models import Appointment, AppointmentStatus, Master, Role, Service, User, WorkingHours
from app.routers.appointments import APPOINTMENT_LOAD, appointment_out
from app.routers.catalog import MASTER_LOAD, master_out
from app.schemas import (
    AppointmentOut,
    ClientOut,
    HoursIn,
    MasterCreate,
    MasterOut,
    MasterUpdate,
    ServiceIn,
    ServiceOut,
    StatusUpdate,
)
from app.security import hash_password
from app.services import analytics

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _own_master_id(db: Db, user: User) -> int:
    master_id = db.scalar(select(Master.id).where(Master.user_id == user.id))
    if master_id is None:
        raise api_error(403, "forbidden")
    return master_id


@router.get("/appointments", response_model=list[AppointmentOut])
def schedule(db: Db, user: StaffUser, on: date, master_id: int | None = None):
    if user.role == Role.master:
        master_id = _own_master_id(db, user)
    start = datetime.combine(on, datetime.min.time(), tzinfo=settings.tz)
    query = (
        select(Appointment)
        .where(Appointment.starts_at >= start, Appointment.starts_at < start + timedelta(days=1))
        .options(*APPOINTMENT_LOAD)
        .order_by(Appointment.starts_at, Appointment.master_id)
    )
    if master_id is not None:
        query = query.where(Appointment.master_id == master_id)
    return [appointment_out(a) for a in db.scalars(query)]


@router.patch("/appointments/{appointment_id}", response_model=AppointmentOut)
def update_status(appointment_id: int, body: StatusUpdate, db: Db, user: StaffUser):
    appointment = db.get(Appointment, appointment_id, options=APPOINTMENT_LOAD)
    if appointment is None:
        raise api_error(404, "appointment_not_found")
    if user.role == Role.master and appointment.master_id != _own_master_id(db, user):
        raise api_error(404, "appointment_not_found")
    if appointment.status != AppointmentStatus.booked or body.status == AppointmentStatus.booked:
        raise api_error(409, "invalid_status_change")
    appointment.status = body.status
    db.commit()
    return appointment_out(appointment)


@router.get("/services", response_model=list[ServiceOut])
def all_services(db: Db, _: AdminUser):
    return db.scalars(select(Service).order_by(Service.category, Service.id)).all()


@router.post("/services", response_model=ServiceOut, status_code=201)
def create_service(body: ServiceIn, db: Db, _: AdminUser):
    service = Service(**body.model_dump())
    db.add(service)
    db.commit()
    return service


@router.put("/services/{service_id}", response_model=ServiceOut)
def update_service(service_id: int, body: ServiceIn, db: Db, _: AdminUser):
    service = db.get(Service, service_id)
    if service is None:
        raise api_error(404, "service_not_found")
    for key, value in body.model_dump().items():
        setattr(service, key, value)
    db.commit()
    return service


def _services_by_ids(db: Db, ids: list[int]) -> list[Service]:
    services = list(db.scalars(select(Service).where(Service.id.in_(ids))))
    if len(services) != len(set(ids)):
        raise api_error(422, "service_not_found")
    return services


def _hours(items: list[HoursIn]) -> list[WorkingHours]:
    if len({h.weekday for h in items}) != len(items) or any(h.start_time >= h.end_time for h in items):
        raise api_error(422, "invalid_hours")
    return [WorkingHours(**h.model_dump()) for h in items]


@router.get("/masters", response_model=list[MasterOut])
def all_masters(db: Db, _: AdminUser):
    return [master_out(m) for m in db.scalars(select(Master).options(*MASTER_LOAD).order_by(Master.id))]


@router.post("/masters", response_model=MasterOut, status_code=201)
def create_master(body: MasterCreate, db: Db, _: AdminUser):
    email = body.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise api_error(409, "email_taken")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        phone=body.phone,
        role=Role.master,
    )
    master = Master(
        user=user,
        title=body.title.model_dump(),
        services=_services_by_ids(db, body.service_ids),
        hours=_hours(body.hours),
    )
    db.add(master)
    db.commit()
    return master_out(master)


@router.put("/masters/{master_id}", response_model=MasterOut)
def update_master(master_id: int, body: MasterUpdate, db: Db, _: AdminUser):
    master = db.get(Master, master_id, options=MASTER_LOAD)
    if master is None:
        raise api_error(404, "master_not_found")
    new_hours = _hours(body.hours)
    master.user.full_name = body.full_name
    master.title = body.title.model_dump()
    master.is_active = body.is_active
    master.services = _services_by_ids(db, body.service_ids)
    # Удаление старых часов до вставки новых: на (master_id, weekday) есть уникальный индекс
    master.hours.clear()
    db.flush()
    master.hours.extend(new_hours)
    db.commit()
    return master_out(master)


@router.get("/clients", response_model=list[ClientOut])
def clients(db: Db, _: AdminUser, q: str | None = Query(default=None, max_length=100)):
    completed = Appointment.status == AppointmentStatus.completed
    query = (
        select(
            User,
            func.count(Appointment.id).filter(completed).label("visits"),
            func.coalesce(func.sum(Appointment.price).filter(completed), 0).label("spent"),
            func.max(Appointment.starts_at).filter(completed).label("last_visit"),
        )
        .outerjoin(Appointment, Appointment.client_id == User.id)
        .where(User.role == Role.client)
        .group_by(User.id)
        .order_by(func.coalesce(func.sum(Appointment.price).filter(completed), 0).desc())
        .limit(200)
    )
    if q:
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(
            User.full_name.ilike(pattern, escape="\\")
            | User.email.ilike(pattern, escape="\\")
            | User.phone.ilike(pattern, escape="\\")
        )
    return [
        ClientOut(
            id=r.User.id,
            full_name=r.User.full_name,
            email=r.User.email,
            phone=r.User.phone,
            visits=r.visits,
            total_spent=float(r.spent),
            last_visit=r.last_visit,
        )
        for r in db.execute(query)
    ]


@router.get("/analytics/overview")
def analytics_overview(db: Db, _: AdminUser, days: int = Query(default=30, ge=7, le=365)):
    return analytics.overview(db, days)


@router.get("/analytics/forecast")
def analytics_forecast(db: Db, _: AdminUser):
    return analytics.demand_forecast(db)
