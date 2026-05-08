"""
model.py — обёртка вокруг обученной модели для использования из API.
"""

from __future__ import annotations

import logging
from pathlib import Path

import joblib
import pandas as pd

from api.train_local import FEATURE_COLS, MODEL_PATH, TYPE_MAP, train_and_save

log = logging.getLogger("model")


class FraudDetector:
    """Singleton-обёртка вокруг sklearn модели."""

    def __init__(self, model_path: Path = MODEL_PATH):
        if not model_path.exists():
            log.warning("Model not found at %s — training a fresh one", model_path)
            train_and_save(model_path)
        self.model = joblib.load(model_path)
        log.info("Model loaded from %s", model_path)

    def predict(self, tx: dict) -> dict:
        type_idx = TYPE_MAP.get(tx.get("type", ""), 0)
        row = pd.DataFrame([{
            "step":           int(tx["step"]),
            "type_idx":       type_idx,
            "amount":         float(tx["amount"]),
            "oldbalanceOrg":  float(tx["oldbalanceOrg"]),
            "newbalanceOrig": float(tx["newbalanceOrig"]),
            "oldbalanceDest": float(tx["oldbalanceDest"]),
            "newbalanceDest": float(tx["newbalanceDest"]),
        }])[FEATURE_COLS]

        proba = float(self.model.predict_proba(row)[0][1])
        return {
            "is_fraud":    int(proba > 0.5),
            "probability": proba,
        }
