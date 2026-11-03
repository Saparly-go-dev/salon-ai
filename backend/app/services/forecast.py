"""Прогноз дневного спроса: градиентный бустинг над календарными и лаговыми признаками.

Модель сравнивается с сезонно-наивным базовым прогнозом ("как в тот же день недели неделю назад")
на отложенных последних днях истории. Прогноз многошаговый: предсказанные значения
подставляются в лаги следующих дней, поэтому проверка повторяет реальные условия работы.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from math import cos, pi, sin

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

MIN_HISTORY_DAYS = 84
HOLDOUT_DAYS = 28


def _features(values: list[float], start: date, index: int) -> list[float]:
    day = start + timedelta(days=index)
    year_angle = 2 * pi * day.timetuple().tm_yday / 365.25
    return [
        day.weekday(),
        sin(year_angle),
        cos(year_angle),
        index,
        values[index - 7],
        values[index - 14],
        values[index - 28],
        float(np.mean(values[index - 7 : index])),
        float(np.mean(values[index - 28 : index])),
    ]


def _fit(values: list[float], start: date) -> GradientBoostingRegressor:
    X = [_features(values, start, i) for i in range(28, len(values))]
    y = values[28:]
    model = GradientBoostingRegressor(
        n_estimators=250, max_depth=3, learning_rate=0.04, subsample=0.85, random_state=42
    )
    model.fit(X, y)
    return model


def _predict(model: GradientBoostingRegressor, values: list[float], start: date, horizon: int) -> list[float]:
    extended = list(values)
    predictions: list[float] = []
    for _ in range(horizon):
        value = max(0.0, float(model.predict([_features(extended, start, len(extended))])[0]))
        predictions.append(value)
        extended.append(value)
    return predictions


def _errors(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    abs_errors = np.abs(actual - predicted)
    total = actual.sum()
    return {
        "mae": round(float(abs_errors.mean()), 2),
        "rmse": round(float(np.sqrt(((actual - predicted) ** 2).mean())), 2),
        # wMAPE устойчив к дням с нулевым спросом, в отличие от обычного MAPE
        "wmape": round(float(abs_errors.sum() / total * 100), 1) if total > 0 else 0.0,
    }


@dataclass
class SeriesForecast:
    predictions: list[float]
    interval: float
    model_metrics: dict[str, float]
    baseline_metrics: dict[str, float]


def forecast_series(values: list[float], start: date, horizon: int = 14) -> SeriesForecast:
    if len(values) < MIN_HISTORY_DAYS:
        raise ValueError(f"Нужно минимум {MIN_HISTORY_DAYS} дней истории")

    train = values[:-HOLDOUT_DAYS]
    actual = np.array(values[-HOLDOUT_DAYS:])
    backtest = np.array(_predict(_fit(train, start), train, start, HOLDOUT_DAYS))
    last_week = train[-7:]
    baseline = np.array([last_week[i % 7] for i in range(HOLDOUT_DAYS)])

    return SeriesForecast(
        predictions=_predict(_fit(values, start), values, start, horizon),
        # Границы: 80-й перцентиль абсолютной ошибки на отложенном периоде
        interval=float(np.quantile(np.abs(actual - backtest), 0.8)),
        model_metrics=_errors(actual, backtest),
        baseline_metrics=_errors(actual, baseline),
    )


def load_level(load: float) -> str:
    if load >= 0.85:
        return "high"
    if load <= 0.45:
        return "low"
    return "normal"
