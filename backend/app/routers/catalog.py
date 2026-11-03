from datetime import date

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.deps import Db, api_error
from app.models import Master, Service
from app.schemas import MasterOut, ServiceOut, SlotOut
from app.services.booking import available_slots

router = APIRouter(prefix="/api", tags=["catalog"])


def master_out(master: Master) -> MasterOut:
    return MasterOut(
        id=master.id,
        full_name=master.user.full_name,
        title=master.title,
        is_active=master.is_active,
        service_ids=[s.id for s in master.services],
        hours=master.hours,
    )


MASTER_LOAD = (selectinload(Master.user), selectinload(Master.services), selectinload(Master.hours))


@router.get("/meta")
def meta():
    return {
        "timezone": settings.salon_timezone,
        "currency": settings.salon_currency,
        "ai_enabled": settings.ai_enabled,
    }


@router.get("/services", response_model=list[ServiceOut])
def services(db: Db):
    return db.scalars(select(Service).where(Service.is_active).order_by(Service.category, Service.id)).all()


@router.get("/masters", response_model=list[MasterOut])
def masters(db: Db, service_id: int | None = None):
    query = select(Master).where(Master.is_active).options(*MASTER_LOAD).order_by(Master.id)
    if service_id is not None:
        query = query.where(Master.services.any(Service.id == service_id))
    return [master_out(m) for m in db.scalars(query)]


@router.get("/availability", response_model=list[SlotOut])
def availability(db: Db, service_id: int, on: date, master_id: int | None = None):
    service = db.get(Service, service_id)
    if service is None or not service.is_active:
        raise api_error(404, "service_not_found")
    return [SlotOut(master_id=s.master_id, master_name=s.master_name, starts_at=s.starts_at) for s in available_slots(db, service, on, master_id)]
