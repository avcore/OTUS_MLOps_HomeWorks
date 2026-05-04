"""
Feast feature definitions.

Что здесь определено:
  - Entity: driver (id водителя такси)
  - DataSource №1: driver_hourly_stats — почасовая агрегатная статистика по водителю
  - DataSource №2: driver_trip_stats   — статистика по поездкам водителя
  - FeatureView №1: driver_hourly_stats_fv  (обязательное задание #1)
  - FeatureView №2: driver_trip_stats_fv     (обязательное задание #1)
  - OnDemandFeatureView: driver_efficiency_odfv  (обязательное задание #2)

Запуск регистрации:
    cd feature_repo
    feast apply
"""

from datetime import timedelta
from pathlib import Path

import pandas as pd
from feast import (
    Entity,
    FeatureView,
    Field,
    FileSource,
    ValueType,
)
from feast.on_demand_feature_view import on_demand_feature_view
from feast.types import Float32, Float64, Int64

# ---------------------------------------------------------------------------
# Пути к источникам данных (parquet файлы, которые создаёт scripts/generate_data.py)
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"

# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------

driver = Entity(
    name="driver",
    join_keys=["driver_id"],
    value_type=ValueType.INT64,
    description="Уникальный идентификатор водителя такси",
)

# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------

driver_hourly_stats_source = FileSource(
    name="driver_hourly_stats_source",
    path=str(DATA_DIR / "driver_hourly_stats.parquet"),
    timestamp_field="event_timestamp",
    created_timestamp_column="created",
    description="Почасовая агрегатная статистика водителя",
)

driver_trip_stats_source = FileSource(
    name="driver_trip_stats_source",
    path=str(DATA_DIR / "driver_trip_stats.parquet"),
    timestamp_field="event_timestamp",
    created_timestamp_column="created",
    description="Статистика по поездкам водителя",
)

# ---------------------------------------------------------------------------
# Feature View #1 — почасовая статистика
# Логически связанные признаки: процент конверсии, процент принятия, среднее число поездок
# ---------------------------------------------------------------------------

driver_hourly_stats_fv = FeatureView(
    name="driver_hourly_stats",
    description="Почасовая агрегатная статистика по работе водителя",
    entities=[driver],
    ttl=timedelta(days=2),
    schema=[
        Field(name="conv_rate",       dtype=Float32, description="Процент завершённых заказов"),
        Field(name="acc_rate",        dtype=Float32, description="Процент принятых заказов"),
        Field(name="avg_daily_trips", dtype=Int64,   description="Среднее число поездок в сутки"),
    ],
    online=True,
    source=driver_hourly_stats_source,
    tags={"team": "ml-ranking", "owner": "mlops-hw4"},
)

# ---------------------------------------------------------------------------
# Feature View #2 — статистика по поездкам
# Логически связанные признаки: общая дистанция, выручка, средний рейтинг
# ---------------------------------------------------------------------------

driver_trip_stats_fv = FeatureView(
    name="driver_trip_stats",
    description="Статистика по поездкам водителя за окно",
    entities=[driver],
    ttl=timedelta(days=7),
    schema=[
        Field(name="total_trips",   dtype=Int64,   description="Всего поездок"),
        Field(name="total_distance_km", dtype=Float64, description="Суммарная дистанция, км"),
        Field(name="total_revenue", dtype=Float64, description="Суммарная выручка, у.е."),
        Field(name="avg_rating",    dtype=Float32, description="Средний рейтинг водителя"),
    ],
    online=True,
    source=driver_trip_stats_source,
    tags={"team": "ml-ranking", "owner": "mlops-hw4"},
)

# ---------------------------------------------------------------------------
# On-Demand Feature View — реальное время
# Считает производные метрики на лету из признаков предыдущих двух FV.
# Используется как для исторического (offline), так и для онлайн-инференса.
# ---------------------------------------------------------------------------

@on_demand_feature_view(
    sources=[driver_hourly_stats_fv, driver_trip_stats_fv],
    schema=[
        Field(name="revenue_per_trip",     dtype=Float64),
        Field(name="distance_per_trip",    dtype=Float64),
        Field(name="effective_conv_score", dtype=Float64),
        Field(name="is_top_driver",        dtype=Int64),
    ],
    description="Производные признаки эффективности водителя, считаются на лету",
)
def driver_efficiency_odfv(features_df: pd.DataFrame) -> pd.DataFrame:
    """
    На входе — DataFrame с колонками из обеих базовых Feature View.
    На выходе — DataFrame с НОВЫМИ колонками, которые объявлены в schema выше.
    """
    out = pd.DataFrame()

    safe_trips = features_df["total_trips"].replace({0: pd.NA})

    out["revenue_per_trip"] = (
        features_df["total_revenue"] / safe_trips
    ).astype("float64").fillna(0.0)

    out["distance_per_trip"] = (
        features_df["total_distance_km"] / safe_trips
    ).astype("float64").fillna(0.0)

    out["effective_conv_score"] = (
        features_df["conv_rate"]
        * features_df["acc_rate"]
        * (features_df["avg_rating"] / 5.0)
    ).astype("float64").fillna(0.0)

    out["is_top_driver"] = (
        (out["revenue_per_trip"] > 50.0) & (features_df["avg_rating"] >= 4.5)
    ).astype("int64")

    return out
