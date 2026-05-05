#!/usr/bin/env python3
"""
Генерирует синтетический parquet с очищенными fraud-данными
(тот же формат, что выдаёт clean_data.py из hw3) и сохраняет локально.
Затем заливаешь его в S3 руками через aws s3 cp.

Запуск:
    pip install pandas pyarrow numpy
    python scripts/generate_fraud_data.py
    aws s3 cp /tmp/fraud_data.parquet \
        s3://<bucket>/cleaned/fraud_transactions/part-00000.parquet \
        --endpoint-url=https://storage.yandexcloud.net --profile yc
"""

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

OUTPUT = Path("/tmp/fraud_data.parquet")
NUM_ROWS = 200_000      # ~200k строк - норм размер для теста ML
SEED = 42

rng = np.random.default_rng(SEED)

types = np.array(["PAYMENT", "TRANSFER", "CASH_OUT", "DEBIT", "CASH_IN"])
type_probs = [0.34, 0.22, 0.22, 0.05, 0.17]

n = NUM_ROWS
df = pd.DataFrame({
    "step":            rng.integers(1, 700, n).astype("int32"),
    "type":            rng.choice(types, n, p=type_probs),
    "amount":          rng.exponential(scale=100_000, size=n).round(2),
    "nameOrig":        np.array([f"C{i}" for i in rng.integers(10_000, 9_999_999, n)]),
    "oldbalanceOrg":   rng.exponential(scale=300_000, size=n).round(2),
    "newbalanceOrig":  np.zeros(n, dtype="float64"),  # пересчитаем ниже
    "nameDest":        np.array([f"M{i}" for i in rng.integers(10_000, 9_999_999, n)]),
    "oldbalanceDest":  rng.exponential(scale=300_000, size=n).round(2),
    "newbalanceDest":  np.zeros(n, dtype="float64"),
    "isFraud":         rng.choice([0, 1], n, p=[0.998, 0.002]).astype("int32"),
    "isFlaggedFraud":  np.zeros(n, dtype="int32"),
})

# Поддерживаем балансовое тождество: для исходящих транзакций
# newbalanceOrig = oldbalanceOrg - amount  (с клиппом до 0)
df["newbalanceOrig"] = (df["oldbalanceOrg"] - df["amount"]).clip(lower=0).round(2)
df["newbalanceDest"] = (df["oldbalanceDest"] + df["amount"]).round(2)

# Для CASH_IN наоборот: новая балансо больше
mask_in = df["type"] == "CASH_IN"
df.loc[mask_in, "newbalanceOrig"] = df.loc[mask_in, "oldbalanceOrg"] + df.loc[mask_in, "amount"]
df.loc[mask_in, "newbalanceDest"] = (df.loc[mask_in, "oldbalanceDest"] - df.loc[mask_in, "amount"]).clip(lower=0)

# Помечаем подозрительно крупные транзакции как isFlaggedFraud
df.loc[df["amount"] > 200_000, "isFlaggedFraud"] = 1

# Делаем мошеннические транзакции "нелогичными" — это поможет модели учиться
fraud_idx = df[df["isFraud"] == 1].index
df.loc[fraud_idx, "amount"] = rng.exponential(scale=500_000, size=len(fraud_idx)).round(2)
df.loc[fraud_idx, "newbalanceOrig"] = 0  # все деньги списали
df.loc[fraud_idx, "newbalanceDest"] = 0  # и не пришли получателю — характерно для фрода

print(f"Сгенерировано {len(df):,} строк")
print(f"  fraud рейт: {df['isFraud'].mean():.4%}")
print(f"  типы: {df['type'].value_counts().to_dict()}")

df.to_parquet(OUTPUT, index=False, engine="pyarrow", compression="snappy")
print(f"Сохранено в {OUTPUT}")
print(f"Размер: {OUTPUT.stat().st_size / 1024 / 1024:.1f} MB")
