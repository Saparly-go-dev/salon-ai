from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models import Appointment, AppointmentStatus
from tests.conftest import auth


def book(client, world, user, hour=10, minute=0, **overrides):
    body = {
        "service_id": world.nails.id,
        "master_id": world.nail_master.id,
        "starts_at": world.at(hour, minute).isoformat(),
        **overrides,
    }
    return client.post("/api/appointments", json=body, headers=auth(user))


def code(response):
    return response.json()["detail"]["code"]


def test_slots_respect_duration_and_working_hours(client, world):
    slots = client.get("/api/availability", params={"service_id": world.nails.id, "on": world.tomorrow.isoformat()}).json()
    starts = [datetime.fromisoformat(s["starts_at"]).astimezone(settings.tz).time().isoformat("minutes") for s in slots]
    assert starts[0] == "09:00"
    # Часовая услуга должна закончиться до 18:00
    assert starts[-1] == "17:00"


def test_booked_time_disappears_from_slots(client, world, db):
    assert book(client, world, world.alice, hour=10).status_code == 201
    slots = client.get("/api/availability", params={"service_id": world.nails.id, "on": world.tomorrow.isoformat()}).json()
    starts = {datetime.fromisoformat(s["starts_at"]).astimezone(settings.tz).time().isoformat("minutes") for s in slots}
    # 09:30 и 10:00 и 10:30 пересекаются с записью 10:00-11:00
    assert not starts & {"09:30", "10:00", "10:30"}
    assert {"09:00", "11:00"} <= starts


def test_overlapping_booking_is_rejected(client, world):
    assert book(client, world, world.alice, hour=10).status_code == 201
    response = book(client, world, world.bob, hour=10, minute=30)
    assert response.status_code == 409 and code(response) == "slot_taken"


def test_concurrent_bookings_only_one_wins(world):
    def attempt(user):
        return book(TestClient(app), world, user, hour=12).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(attempt, [world.alice, world.bob] * 4))
    assert statuses.count(201) == 1
    assert statuses.count(409) == 7


def test_cancelled_slot_can_be_rebooked(client, world):
    first = book(client, world, world.alice, hour=10).json()
    assert client.post(f"/api/appointments/{first['id']}/cancel", headers=auth(world.alice)).status_code == 200
    assert book(client, world, world.bob, hour=10).status_code == 201


def test_rejects_past_outside_hours_and_wrong_master(client, world):
    yesterday = world.tomorrow - timedelta(days=2)
    past = book(client, world, world.alice, starts_at=world.at(10, day=yesterday).isoformat())
    assert code(past) == "slot_in_past"
    assert code(book(client, world, world.alice, hour=17, minute=30)) == "outside_working_hours"
    assert code(book(client, world, world.alice, master_id=world.hair_master.id)) == "master_cannot_do_service"


def test_naive_datetime_is_rejected(client, world):
    response = book(client, world, world.alice, starts_at=f"{world.tomorrow}T10:00:00")
    assert response.status_code == 422


def test_client_cannot_cancel_or_book_for_others(client, world):
    appointment = book(client, world, world.alice).json()
    response = client.post(f"/api/appointments/{appointment['id']}/cancel", headers=auth(world.bob))
    assert response.status_code == 404
    assert book(client, world, world.bob, hour=12, client_id=world.alice.id).status_code == 403


def test_admin_books_for_client(client, world):
    response = book(client, world, world.admin, client_id=world.alice.id)
    assert response.status_code == 201
    assert response.json()["client_id"] == world.alice.id
    assert response.json()["source"] == "admin"


def test_price_is_fixed_at_booking_time(client, world, db):
    appointment = book(client, world, world.alice).json()
    body = {"category": "nails", "name": world.nails.name, "duration_minutes": 60, "price": "999"}
    assert client.put(f"/api/admin/services/{world.nails.id}", json=body, headers=auth(world.admin)).status_code == 200
    assert db.get(Appointment, appointment["id"]).price == 100


def test_status_change_rules(client, world):
    appointment = book(client, world, world.alice).json()
    url = f"/api/admin/appointments/{appointment['id']}"
    assert client.patch(url, json={"status": "completed"}, headers=auth(world.alice)).status_code == 403
    # Мастер не видит чужие записи
    assert client.patch(url, json={"status": "completed"}, headers=auth(world.hair_user)).status_code == 404
    assert client.patch(url, json={"status": "completed"}, headers=auth(world.nail_user)).status_code == 200
    # Завершённую запись нельзя изменить повторно
    assert client.patch(url, json={"status": "no_show"}, headers=auth(world.admin)).status_code == 409


def test_master_schedule_shows_only_own(client, world):
    book(client, world, world.alice)
    params = {"on": world.tomorrow.isoformat()}
    own = client.get("/api/admin/appointments", params=params, headers=auth(world.nail_user)).json()
    other = client.get("/api/admin/appointments", params={**params, "master_id": world.nail_master.id}, headers=auth(world.hair_user)).json()
    assert len(own) == 1 and other == []
