"""
Генерирует синтетические parquet-данные для feature repo.

Запуск:
    python scripts/generate_data.py

Создаёт два файла в feature_repo/data/:
  - driver_hourly_stats.parquet
  - driver_trip_stats.parquet
"""

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "feature_repo" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

NUM_DRIVERS = 10
NUM_HOURS   = 24 * 14  # две недели почасовых снимков
SEED        = 42

rng = np.random.default_rng(SEED)
now = datetime.utcnow().replace(microsecond=0, second=0, minute=0)


def generate_hourly_stats() -> pd.DataFrame:
    rows = []
    for driver_id in range(1001, 1001 + NUM_DRIVERS):
        for h in range(NUM_HOURS):
            ts = now - timedelta(hours=h)
            rows.append(
                dict(
                    driver_id=driver_id,
                    event_timestamp=ts,
                    created=ts,
                    conv_rate=float(rng.uniform(0.4, 0.95)),
                    acc_rate=float(rng.uniform(0.5, 0.99)),
                    avg_daily_trips=int(rng.integers(5, 60)),
                )
            )
    return pd.DataFrame(rows)


def generate_trip_stats() -> pd.DataFrame:
    rows = []
    for driver_id in range(1001, 1001 + NUM_DRIVERS):
        for h in range(NUM_HOURS):
            ts = now - timedelta(hours=h)
            trips = int(rng.integers(0, 8))
            rows.append(
                dict(
                    driver_id=driver_id,
                    event_timestamp=ts,
                    created=ts,
                    total_trips=trips,
                    total_distance_km=float(rng.uniform(0, 80) if trips else 0.0),
                    total_revenue=float(rng.uniform(0, 600) if trips else 0.0),
                    avg_rating=float(rng.uniform(3.5, 5.0)),
                )
            )
    return pd.DataFrame(rows)


def main() -> None:
    print(f"Генерирую данные для {NUM_DRIVERS} водителей x {NUM_HOURS} часов...")

    hourly = generate_hourly_stats()
    trips  = generate_trip_stats()

    hourly_path = DATA_DIR / "driver_hourly_stats.parquet"
    trips_path  = DATA_DIR / "driver_trip_stats.parquet"

    hourly.to_parquet(hourly_path, index=False)
    trips.to_parquet(trips_path,  index=False)

    print(f"  -> {hourly_path}  ({len(hourly):,} строк)")
    print(f"  -> {trips_path}   ({len(trips):,} строк)")
    print("Готово.")


if __name__ == "__main__":
    main()
