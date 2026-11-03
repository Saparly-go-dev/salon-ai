from datetime import UTC, date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import Appointment, AppointmentStatus, Master, Role, Service, User
from app.services import forecast as fc

COMPLETED = AppointmentStatus.completed


def _local(column):
    return func.timezone(settings.salon_timezone, column)


def _local_date(column):
    return func.date(_local(column))


def today() -> date:
    return datetime.now(settings.tz).date()


def _day_start(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=settings.tz)


def _period_kpis(db: Session, start: datetime, end: datetime) -> dict:
    row = db.execute(
        select(
            func.count().label("total"),
            func.count().filter(Appointment.status == COMPLETED).label("completed"),
            func.count().filter(Appointment.status == AppointmentStatus.cancelled).label("cancelled"),
            func.count().filter(Appointment.status == AppointmentStatus.no_show).label("no_show"),
            func.coalesce(func.sum(Appointment.price).filter(Appointment.status == COMPLETED), 0).label("revenue"),
        ).where(Appointment.starts_at >= start, Appointment.starts_at < end)
    ).one()
    new_clients = db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.role == Role.client, User.created_at >= start, User.created_at < end)
    )
    revenue = float(row.revenue)
    return {
        "revenue": round(revenue, 2),
        "completed": row.completed,
        "avg_ticket": round(revenue / row.completed, 2) if row.completed else 0,
        "cancel_rate": round(row.cancelled / row.total * 100, 1) if row.total else 0,
        "no_show_rate": round(row.no_show / row.total * 100, 1) if row.total else 0,
        "new_clients": new_clients,
    }


def _weekday_capacity_minutes(masters: list[Master]) -> dict[int, int]:
    capacity = dict.fromkeys(range(7), 0)
    for master in masters:
        for hours in master.hours:
            minutes = (hours.end_time.hour * 60 + hours.end_time.minute) - (
                hours.start_time.hour * 60 + hours.start_time.minute
            )
            capacity[hours.weekday] += minutes
    return capacity


def overview(db: Session, days: int) -> dict:
    last_day = today()
    first_day = last_day - timedelta(days=days - 1)
    start = _day_start(first_day)
    end = _day_start(last_day + timedelta(days=1))
    previous_start = start - timedelta(days=days)

    daily_rows = db.execute(
        select(
            _local_date(Appointment.starts_at).label("day"),
            func.count().label("appointments"),
            func.coalesce(func.sum(Appointment.price), 0).label("revenue"),
        )
        .where(Appointment.status == COMPLETED, Appointment.starts_at >= start, Appointment.starts_at < end)
        .group_by("day")
    ).all()
    by_day = {r.day: r for r in daily_rows}
    daily = []
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        row = by_day.get(day)
        daily.append(
            {
                "date": day.isoformat(),
                "appointments": row.appointments if row else 0,
                "revenue": float(row.revenue) if row else 0,
            }
        )

    top_services = db.execute(
        select(
            Service.id,
            Service.name,
            func.count().label("count"),
            func.sum(Appointment.price).label("revenue"),
        )
        .join(Appointment, Appointment.service_id == Service.id)
        .where(Appointment.status == COMPLETED, Appointment.starts_at >= start, Appointment.starts_at < end)
        .group_by(Service.id)
        .order_by(func.sum(Appointment.price).desc())
        .limit(6)
    ).all()

    masters = list(
        db.scalars(select(Master).where(Master.is_active).options(selectinload(Master.hours), selectinload(Master.user)))
    )
    booked = {
        r.master_id: r
        for r in db.execute(
            select(
                Appointment.master_id,
                func.count().label("count"),
                func.sum(Appointment.price).label("revenue"),
                func.sum(func.extract("epoch", Appointment.ends_at - Appointment.starts_at) / 60).label("minutes"),
            )
            .where(Appointment.status == COMPLETED, Appointment.starts_at >= start, Appointment.starts_at < end)
            .group_by(Appointment.master_id)
        )
    }
    master_stats = []
    for master in masters:
        capacity_by_day = _weekday_capacity_minutes([master])
        capacity = sum(capacity_by_day[(first_day + timedelta(days=i)).weekday()] for i in range(days))
        row = booked.get(master.id)
        minutes = float(row.minutes) if row else 0
        master_stats.append(
            {
                "id": master.id,
                "name": master.user.full_name,
                "appointments": row.count if row else 0,
                "revenue": float(row.revenue) if row else 0,
                "utilization": round(minutes / capacity * 100, 1) if capacity else 0,
            }
        )
    master_stats.sort(key=lambda m: m["revenue"], reverse=True)

    local_start = _local(Appointment.starts_at)
    heatmap = [
        {"weekday": int(r.dow) - 1, "hour": int(r.hour), "count": r.count}
        for r in db.execute(
            select(
                func.extract("isodow", local_start).label("dow"),
                func.extract("hour", local_start).label("hour"),
                func.count().label("count"),
            )
            .where(Appointment.status == COMPLETED, Appointment.starts_at >= start, Appointment.starts_at < end)
            .group_by("dow", "hour")
        )
    ]

    return {
        "days": days,
        "kpis": _period_kpis(db, start, end),
        "previous_kpis": _period_kpis(db, previous_start, start),
        "daily": daily,
        "top_services": [
            {"id": r.id, "name": r.name, "count": r.count, "revenue": float(r.revenue)} for r in top_services
        ],
        "masters": master_stats,
        "heatmap": heatmap,
    }


def demand_forecast(db: Session, horizon: int = 14) -> dict:
    last_history_day = today() - timedelta(days=1)
    first_row = db.scalar(
        select(func.min(_local_date(Appointment.starts_at))).where(Appointment.status == COMPLETED)
    )
    if first_row is None or (last_history_day - first_row).days + 1 < fc.MIN_HISTORY_DAYS:
        return {"available": False, "min_history_days": fc.MIN_HISTORY_DAYS}

    rows = db.execute(
        select(
            _local_date(Appointment.starts_at).label("day"),
            func.count().label("appointments"),
            func.sum(Appointment.price).label("revenue"),
        )
        .where(Appointment.status == COMPLETED, Appointment.starts_at < _day_start(today()))
        .group_by("day")
    ).all()
    by_day = {r.day: r for r in rows}
    length = (last_history_day - first_row).days + 1
    dates = [first_row + timedelta(days=i) for i in range(length)]
    appointments = [float(by_day[d].appointments) if d in by_day else 0.0 for d in dates]
    revenue = [float(by_day[d].revenue) if d in by_day else 0.0 for d in dates]

    demand = fc.forecast_series(appointments, first_row, horizon)
    income = fc.forecast_series(revenue, first_row, horizon)

    masters = list(db.scalars(select(Master).where(Master.is_active).options(selectinload(Master.hours))))
    capacity = _weekday_capacity_minutes(masters)
    avg_minutes = (
        db.scalar(
            select(func.avg(func.extract("epoch", Appointment.ends_at - Appointment.starts_at) / 60)).where(
                Appointment.status == COMPLETED,
                Appointment.starts_at >= datetime.now(UTC) - timedelta(days=60),
            )
        )
        or 60
    )

    first_forecast = today()
    booked_rows = db.execute(
        select(_local_date(Appointment.starts_at).label("day"), func.count().label("count"))
        .where(
            Appointment.status == AppointmentStatus.booked,
            Appointment.starts_at >= _day_start(first_forecast),
            Appointment.starts_at < _day_start(first_forecast + timedelta(days=horizon)),
        )
        .group_by("day")
    ).all()
    booked = {r.day: r.count for r in booked_rows}

    points = []
    for offset in range(horizon):
        day = first_forecast + timedelta(days=offset)
        predicted = demand.predictions[offset]
        minutes = capacity[day.weekday()]
        load = predicted * float(avg_minutes) / minutes if minutes else 0
        points.append(
            {
                "date": day.isoformat(),
                "appointments": round(predicted, 1),
                "low": round(max(0, predicted - demand.interval), 1),
                "high": round(predicted + demand.interval, 1),
                "revenue": round(income.predictions[offset], 2),
                "booked": booked.get(day, 0),
                "load": round(load * 100, 1),
                "level": fc.load_level(load),
            }
        )

    return {
        "available": True,
        "history": [
            {"date": d.isoformat(), "appointments": appointments[-28 + i]} for i, d in enumerate(dates[-28:])
        ],
        "forecast": points,
        "metrics": {
            "holdout_days": fc.HOLDOUT_DAYS,
            "model": demand.model_metrics,
            "baseline": demand.baseline_metrics,
        },
    }
