# Minimal data preparation script.
# Loads `data/raw/transactions.csv` (if exists) and produces `data/processed/train.csv`.
# If no data is found, it will generate a small synthetic dataset for demonstration.

from __future__ import annotations
import os
import pandas as pd
import numpy as np
from pathlib import Path

RAW = Path("data/raw/transactions.csv")
OUT = Path("data/processed/train.csv")

def generate_synthetic(n_samples: int = 5000, fraud_rate: float = 0.02) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    amount = rng.gamma(shape=2.0, scale=50.0, size=n_samples)  # transaction amount
    hour = rng.integers(0, 24, size=n_samples)                 # hour of day
    country_risk = rng.uniform(0, 1, size=n_samples)           # country risk score
    # fraud probability increases with amount and country risk, and at night hours
    prob = 0.5*(amount/amount.max()) + 0.4*country_risk + 0.1*( (hour>=0)&(hour<=6) )
    prob = (prob - prob.min())/(prob.max()-prob.min())
    y = (rng.uniform(0,1,size=n_samples) < (prob * (fraud_rate/np.mean(prob)))).astype(int)
    df = pd.DataFrame({"amount":amount, "hour":hour, "country_risk":country_risk, "is_fraud":y})
    return df

def main():
    os.makedirs(OUT.parent, exist_ok=True)
    if RAW.exists():
        df = pd.read_csv(RAW)
        # minimal cleaning example
        df = df.dropna().reset_index(drop=True)
    else:
        df = generate_synthetic()
    df.to_csv(OUT, index=False)
    print(f"[data_prep] wrote {OUT} with shape {df.shape}")

if __name__ == "__main__":
    main()