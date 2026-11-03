import random
from datetime import date, timedelta

import pytest

from app.config import settings
from app.models import Appointment, AppointmentStatus
from app.services.analytics import demand_forecast, overview, today
from app.services.forecast import MIN_HISTORY_DAYS, forecast_series, load_level
from tests.conftest import auth

WEEK = [10, 11, 12, 14, 18, 22, 13]


def weekly_series(days, noise=1.0, seed=1):
    rng = random.Random(seed)
    return [max(0.0, WEEK[i % 7] + rng.gauss(0, noise)) for i in range(days)]


def test_requires_minimum_history():
    with pytest.raises(ValueError):
        forecast_series([1.0] * (MIN_HISTORY_DAYS - 1), date(2026, 1, 5))


def test_learns_weekly_pattern():
    # Ряд начинается в понедельник: индекс 5 - суббота, пик спроса
    start = date(2026, 1, 5)
    result = forecast_series(weekly_series(364), start, horizon=7)
    assert all(abs(p - w) < 3 for p, w in zip(result.predictions, WEEK))
    assert result.predictions[5] == max(result.predictions)
    assert result.model_metrics["mae"] < 3


def test_beats_baseline_on_noisy_trend():
    start = date(2026, 1, 5)
    rng = random.Random(7)
    series = [(WEEK[i % 7] + i * 0.02) * rng.lognormvariate(0, 0.12) for i in range(364)]
    result = forecast_series(series, start, horizon=14)
    assert result.model_metrics["mae"] < result.baseline_metrics["mae"]
    assert len(result.predictions) == 14 and min(result.predictions) >= 0


def test_load_levels():
    assert load_level(0.9) == "high"
    assert load_level(0.6) == "normal"
    assert load_level(0.3) == "low"


def seed_history(db, world, days):
    # По одной завершённой записи в день в разное время, без пересечений
    base = today()
    for age in range(1, days + 1):
        day = base - timedelta(days=age)
        db.add(
            Appointment(
                client_id=world.alice.id,
                master_id=world.nail_master.id,
                service_id=world.nails.id,
                starts_at=world.at(10, day=day),
                ends_at=world.at(11, day=day),
                price=100,
                status=AppointmentStatus.completed,
            )
        )
    db.commit()


def test_forecast_unavailable_with_short_history(db, world):
    seed_history(db, world, 10)
    assert demand_forecast(db)["available"] is False


def test_forecast_endpoint(db, world, client):
    seed_history(db, world, 100)
    data = client.get("/api/admin/analytics/forecast", headers=auth(world.admin)).json()
    assert data["available"] is True
    assert len(data["forecast"]) == 14 and len(data["history"]) == 28
    assert data["forecast"][0]["date"] == today().isoformat()
    # Постоянный спрос: одна запись в день
    assert abs(data["forecast"][0]["appointments"] - 1) < 0.2
    # 60 минут на 18 часов суммарной ёмкости двух мастеров
    assert abs(data["forecast"][0]["load"] - 100 * 60 / (18 * 60)) < 2


def test_overview_counts_only_completed_revenue(db, world):
    seed_history(db, world, 40)
    day = today() - timedelta(days=1)
    db.add(
        Appointment(
            client_id=world.bob.id,
            master_id=world.nail_master.id,
            service_id=world.nails.id,
            starts_at=world.at(15, day=day),
            ends_at=world.at(16, day=day),
            price=500,
            status=AppointmentStatus.cancelled,
        )
    )
    db.commit()
    data = overview(db, 30)
    assert data["kpis"]["completed"] == 29  # сегодняшний день ещё без истории
    assert data["kpis"]["revenue"] == 2900
    assert data["kpis"]["avg_ticket"] == 100
    assert data["kpis"]["cancel_rate"] > 0
    assert data["daily"][-2]["appointments"] == 1
    assert data["top_services"][0]["id"] == world.nails.id
    assert {h["hour"] for h in data["heatmap"]} == {10}
