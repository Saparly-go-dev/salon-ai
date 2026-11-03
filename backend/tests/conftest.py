import os

os.environ["DATABASE_URL"] = "postgresql+psycopg://localhost/salon_ai_test"
os.environ["ANTHROPIC_API_KEY"] = ""

from datetime import date, datetime, time, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.deps import rate_limiter  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Master, Role, Service, User, WorkingHours  # noqa: E402
from app.security import create_token, hash_password  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def schema():
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def clean():
    rate_limiter.reset()
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    return TestClient(app)


def make_user(db, email, role=Role.client, name="Test User"):
    user = User(email=email, password_hash=hash_password("Password1!"), full_name=name, role=role)
    db.add(user)
    db.commit()
    return user


def auth(user):
    return {"Authorization": f"Bearer {create_token(user.id)}"}


class World:
    """Салон из двух услуг и двух мастеров, которые работают каждый день с 9 до 18."""


@pytest.fixture
def world(db):
    w = World()
    w.admin = make_user(db, "admin@t.io", Role.admin)
    w.alice = make_user(db, "alice@t.io", name="Alice")
    w.bob = make_user(db, "bob@t.io", name="Bob")
    w.nails = Service(category="nails", name={"tk": "Dyrnak", "ru": "Маникюр", "en": "Manicure"}, description={}, duration_minutes=60, price=100)
    w.hair = Service(category="hair", name={"tk": "Saç", "ru": "Стрижка", "en": "Haircut"}, description={}, duration_minutes=30, price=50)
    db.add_all([w.nails, w.hair])
    w.nail_user = make_user(db, "m1@t.io", Role.master, "Nail Master")
    w.hair_user = make_user(db, "m2@t.io", Role.master, "Hair Master")
    hours = lambda: [WorkingHours(weekday=d, start_time=time(9), end_time=time(18)) for d in range(7)]  # noqa: E731
    w.nail_master = Master(user=w.nail_user, title={}, services=[w.nails], hours=hours())
    w.hair_master = Master(user=w.hair_user, title={}, services=[w.hair], hours=hours())
    db.add_all([w.nail_master, w.hair_master])
    db.commit()
    w.tomorrow = datetime.now(settings.tz).date() + timedelta(days=1)
    w.at = lambda hour, minute=0, day=None: datetime.combine(day or w.tomorrow, time(hour, minute), tzinfo=settings.tz)
    return w
