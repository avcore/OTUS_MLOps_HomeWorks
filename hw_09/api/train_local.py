"""
train_local.py — обучение локальной dummy-модели для API.

Используется при сборке Docker image, чтобы внутри контейнера лежал
файл model.pkl. В реальном проекте сюда подставлялась бы модель из
MLflow Model Registry, но для зачёта hw9 достаточно простого RF.

Запуск:
    python -m api.train_local
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

MODEL_PATH = Path(__file__).parent / "model.pkl"

FEATURE_COLS = [
    "step",
    "type_idx",
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
]

TYPE_MAP = {"PAYMENT": 0, "TRANSFER": 1, "CASH_OUT": 2, "DEBIT": 3, "CASH_IN": 4}


def generate_synthetic(n: int = 5000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "step":           rng.integers(1, 700, n),
        "type_idx":       rng.integers(0, 5, n),
        "amount":         rng.exponential(100_000, n),
        "oldbalanceOrg":  rng.exponential(300_000, n),
        "newbalanceOrig": rng.exponential(300_000, n),
        "oldbalanceDest": rng.exponential(300_000, n),
        "newbalanceDest": rng.exponential(300_000, n),
    })
    # «Мошеннические» = крупные TRANSFER/CASH_OUT с обнулённым счётом получателя
    df["isFraud"] = (
        (df["amount"] > 200_000)
        & (df["type_idx"].isin([1, 2]))
        & (df["newbalanceDest"] < 1_000)
    ).astype(int)
    return df


def train_and_save(out_path: Path = MODEL_PATH) -> None:
    df = generate_synthetic()
    X = df[FEATURE_COLS]
    y = df["isFraud"]

    model = RandomForestClassifier(
        n_estimators=30, max_depth=8, random_state=42, n_jobs=-1,
    )
    model.fit(X, y)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out_path)
    print(f"Model saved to {out_path}, fraud rate in train: {y.mean():.4f}")


if __name__ == "__main__":
    train_and_save()
