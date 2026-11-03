"""Демонстрационные данные: каталог, сотрудники и синтетическая история записей за год.

Запуск: python -m app.seed [--reset]
История сгенерирована и нужна, чтобы показать аналитику и обучить модель прогноза.
Метрики прогноза на этих данных не являются результатами реального салона.
"""

import argparse
import random
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from math import cos, exp, pi

from sqlalchemy import select, text

from app.config import settings
from app.db import SessionLocal
from app.models import Appointment, AppointmentSource, AppointmentStatus, Master, Role, Service, User, WorkingHours
from app.security import hash_password

ADMIN_PASSWORD = "Admin123!"
STAFF_PASSWORD = "Master123!"
CLIENT_PASSWORD = "Client123!"
HISTORY_DAYS = 365
SEED = 20261103


def _l(tk, ru, en):
    return {"tk": tk, "ru": ru, "en": en}


SERVICES = [
    ("hair", _l("Aýal saç kesimi", "Женская стрижка", "Women's haircut"), _l("Ýuwmak, kesmek we düzmek", "Мытьё, стрижка и укладка", "Wash, cut and styling"), 60, 150, 10),
    ("hair", _l("Erkek saç kesimi", "Мужская стрижка", "Men's haircut"), _l("Klassiki ýa-da häzirki zaman kesim", "Классическая или современная стрижка", "Classic or modern cut"), 30, 80, 8),
    ("hair", _l("Saç boýamak", "Окрашивание волос", "Hair colouring"), _l("Bir reňkli boýamak we ideg", "Однотонное окрашивание с уходом", "Single-colour dyeing with care"), 120, 350, 5),
    ("hair", _l("Baýramçylyk saç düzümi", "Вечерняя причёска", "Evening hairstyle"), _l("Baýramçylyk üçin saç düzümi", "Причёска для торжества", "Styling for a special occasion"), 60, 200, 3),
    ("nails", _l("Klassiki manikýur", "Классический маникюр", "Classic manicure"), _l("Dyrnaklara we kutikula ideg", "Обработка ногтей и кутикулы", "Nail and cuticle care"), 60, 120, 10),
    ("nails", _l("Manikýur we gel-lak", "Маникюр с гель-лаком", "Gel polish manicure"), _l("Manikýur we uzak saklanýan örtük", "Маникюр и стойкое покрытие", "Manicure with long-lasting polish"), 90, 200, 12),
    ("nails", _l("Dyrnak dizaýny", "Дизайн ногтей", "Nail art"), _l("Çylşyrymly çeper dizaýn", "Сложный художественный дизайн", "Detailed artistic design"), 120, 280, 6),
    ("nails", _l("Dyrnak uzaltmak", "Наращивание ногтей", "Nail extensions"), _l("Gel bilen uzaltmak we örtük", "Наращивание гелем с покрытием", "Gel extensions with polish"), 150, 380, 4),
    ("nails", _l("Pedikýur", "Педикюр", "Pedicure"), _l("Aýaklara we dyrnaklara ideg", "Уход за стопами и ногтями", "Foot and nail care"), 75, 180, 6),
    ("face", _l("Ýüz arassalamak", "Чистка лица", "Facial cleansing"), _l("Kosmetiki arassalamak we maska", "Косметическая чистка и маска", "Cosmetic cleansing and mask"), 60, 220, 5),
    ("brows", _l("Gaş we kirpik boýamak", "Окрашивание бровей и ресниц", "Brow and lash tint"), _l("Şekil bermek we boýamak", "Коррекция формы и окрашивание", "Shaping and tinting"), 30, 90, 7),
    ("makeup", _l("Baýramçylyk makiýaž", "Вечерний макияж", "Evening make-up"), _l("Baýramçylyk üçin makiýaž", "Макияж для торжества", "Make-up for a special occasion"), 60, 250, 3),
]

# (имя, почта, должность, категории услуг, выходные дни)
MASTERS = [
    ("Aýna Berdiýewa", "ayna", _l("Saç ussasy", "Парикмахер-стилист", "Hair stylist"), ("hair",), (0,)),
    ("Merdan Annaýew", "merdan", _l("Saç ussasy", "Парикмахер", "Hairdresser"), ("hair",), (6,)),
    ("Jeren Orazowa", "jeren", _l("Dyrnak ussasy", "Мастер ногтевого сервиса", "Nail technician"), ("nails",), (1,)),
    ("Bahar Saparowa", "bahar", _l("Dyrnak ussasy", "Мастер ногтевого сервиса", "Nail technician"), ("nails",), (3,)),
    ("Leýla Nuryýewa", "leyla", _l("Kosmetolog we wizažist", "Косметолог и визажист", "Beautician and make-up artist"), ("face", "brows", "makeup"), (2,)),
]

CLIENT_FIRST = ["Maral", "Ogulgerek", "Gözel", "Selbi", "Altyn", "Aýjemal", "Enejan", "Mähri", "Sona", "Gülşat", "Nurana", "Oguljeren"]
CLIENT_LAST = ["Ataýewa", "Hojaýewa", "Gurbanowa", "Rejepowa", "Durdyýewa", "Çaryýewa", "Meredowa", "Babaýewa"]


def _daily_demand(rng: random.Random, day: date, age_days: int) -> int:
    weekday_factor = [0.72, 0.78, 0.85, 0.95, 1.2, 1.4, 0.9][day.weekday()]
    trend = 1 + 0.22 * (1 - age_days / HISTORY_DAYS)
    season = 1 + 0.12 * cos(2 * pi * (day.timetuple().tm_yday - 350) / 365.25)
    # Предпраздничный рост: Новый год и 8 марта
    peak = 0.0
    for month, dom in ((12, 31), (3, 8)):
        target = date(day.year, month, dom)
        distance = (target - day).days
        if 0 <= distance <= 6:
            peak = max(peak, 0.45 * exp(-distance / 3))
    return max(0, round(17 * weekday_factor * trend * season * (1 + peak) * rng.lognormvariate(0, 0.13)))


def _fill_day(rng, day, demand, services_weighted, masters_by_category, clients, make_appointment):
    busy: dict[int, datetime] = {}
    for _ in range(demand):
        service = rng.choices(services_weighted[0], services_weighted[1])[0]
        candidates = [m for m in masters_by_category[service.category] if day.weekday() in {h.weekday for h in m.hours}]
        rng.shuffle(candidates)
        for master in candidates:
            hours = next(h for h in master.hours if h.weekday == day.weekday())
            opening = datetime.combine(day, hours.start_time, tzinfo=settings.tz)
            closing = datetime.combine(day, hours.end_time, tzinfo=settings.tz)
            # Небольшие паузы между клиентами, чтобы день выглядел реалистично
            start = busy.get(master.id, opening) + timedelta(minutes=rng.choice((0, 0, 0, 30, 60)))
            end = start + timedelta(minutes=service.duration_minutes)
            if end <= closing:
                busy[master.id] = end
                make_appointment(rng.choice(clients), master, service, start, end)
                break


def seed(reset: bool = False) -> None:
    with SessionLocal() as db:
        if db.scalar(select(User.id).limit(1)) is not None:
            if not reset:
                print("База уже содержит данные. Для пересоздания: python -m app.seed --reset")
                return
            db.execute(
                text(
                    "TRUNCATE nail_analyses, conversations, appointments, working_hours, master_services, "
                    "masters, services, users RESTART IDENTITY CASCADE"
                )
            )
            db.commit()

        rng = random.Random(SEED)
        now = datetime.now(UTC)
        today = now.astimezone(settings.tz).date()

        admin = User(email="admin@salon.demo", password_hash=hash_password(ADMIN_PASSWORD), full_name="Administrator", role=Role.admin)
        db.add(admin)

        services = []
        weights = []
        for category, name, description, minutes, price, weight in SERVICES:
            service = Service(category=category, name=name, description=description, duration_minutes=minutes, price=Decimal(price))
            services.append(service)
            weights.append(weight)
        db.add_all(services)

        staff_hash = hash_password(STAFF_PASSWORD)
        masters_by_category: dict[str, list[Master]] = {}
        for full_name, login, title, categories, days_off in MASTERS:
            user = User(email=f"{login}@salon.demo", password_hash=staff_hash, full_name=full_name, role=Role.master, phone=f"+99361{rng.randint(100000, 999999)}")
            master = Master(
                user=user,
                title=title,
                services=[s for s in services if s.category in categories],
                hours=[
                    WorkingHours(weekday=d, start_time=time(9), end_time=time(19))
                    for d in range(7)
                    if d not in days_off
                ],
            )
            db.add(master)
            for category in categories:
                masters_by_category.setdefault(category, []).append(master)

        client_hash = hash_password(CLIENT_PASSWORD)
        demo_client = User(email="client@salon.demo", password_hash=client_hash, full_name="Maral Ataýewa", role=Role.client, phone="+99365000001", created_at=now - timedelta(days=HISTORY_DAYS + 30))
        clients = [demo_client]
        for i in range(120):
            joined = now - timedelta(days=rng.randint(1, HISTORY_DAYS + 30))
            clients.append(
                User(
                    email=f"client{i + 1}@salon.demo",
                    password_hash=client_hash,
                    full_name=f"{rng.choice(CLIENT_FIRST)} {rng.choice(CLIENT_LAST)}",
                    role=Role.client,
                    phone=f"+99365{rng.randint(100000, 999999)}",
                    created_at=joined,
                )
            )
        db.add_all(clients)
        db.flush()

        appointments: list[Appointment] = []

        def history_appointment(client, master, service, start, end):
            status = rng.choices(
                (AppointmentStatus.completed, AppointmentStatus.cancelled, AppointmentStatus.no_show),
                (0.89, 0.07, 0.04),
            )[0]
            appointments.append(
                Appointment(client_id=client.id, master_id=master.id, service_id=service.id, starts_at=start, ends_at=end, price=service.price, status=status, source=AppointmentSource.web, created_at=start - timedelta(days=rng.randint(0, 10)))
            )

        def future_appointment(client, master, service, start, end):
            if start > now:
                appointments.append(
                    Appointment(client_id=client.id, master_id=master.id, service_id=service.id, starts_at=start, ends_at=end, price=service.price, status=AppointmentStatus.booked, source=rng.choice((AppointmentSource.web, AppointmentSource.admin)))
                )

        for age in range(HISTORY_DAYS, 0, -1):
            day = today - timedelta(days=age)
            _fill_day(rng, day, _daily_demand(rng, day, age), (services, weights), masters_by_category, clients, history_appointment)

        # Сегодня: прошедшие визиты уже завершены, остальные ещё впереди
        def today_appointment(client, master, service, start, end):
            status = AppointmentStatus.completed if end <= now else AppointmentStatus.booked
            appointments.append(
                Appointment(client_id=client.id, master_id=master.id, service_id=service.id, starts_at=start, ends_at=end, price=service.price, status=status, source=AppointmentSource.web)
            )

        _fill_day(rng, today, _daily_demand(rng, today, 0), (services, weights), masters_by_category, clients, today_appointment)

        # Будущие записи: чем дальше дата, тем меньше уже занято
        for ahead in range(1, 10):
            day = today + timedelta(days=ahead)
            share = max(0.08, 0.6 - 0.07 * ahead)
            _fill_day(rng, day, round(_daily_demand(rng, day, 0) * share), (services, weights), masters_by_category, clients, future_appointment)

        db.add_all(appointments)
        db.commit()
        print(f"Готово: услуг {len(services)}, мастеров {len(MASTERS)}, клиентов {len(clients)}, записей {len(appointments)}")
        print(f"Администратор: admin@salon.demo / {ADMIN_PASSWORD}")
        print(f"Мастер:        jeren@salon.demo / {STAFF_PASSWORD}")
        print(f"Клиент:        client@salon.demo / {CLIENT_PASSWORD}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="удалить все данные и создать заново")
    seed(parser.parse_args().reset)
