"""
main.py — FastAPI приложение для inference fraud-детектора.

Endpoint'ы:
  GET  /health     — проверка живости (для k8s readiness/liveness probe)
  GET  /version    — информация об API
  POST /predict    — предсказание fraud по одной транзакции

В hw10 сюда же добавлен /metrics (Prometheus) — но это в hw10 ветке.
"""

from __future__ import annotations

import logging
import os
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from api.model import FraudDetector

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("api")

API_VERSION = os.environ.get("API_VERSION", "1.0.0")

app = FastAPI(
    title="Fraud Detection API",
    description="REST API для предсказания мошеннических транзакций",
    version=API_VERSION,
)

detector: FraudDetector | None = None


@app.on_event("startup")
def _startup() -> None:
    global detector
    detector = FraudDetector()


# --------------------------------------------------------------------------- #
#  Schemas
# --------------------------------------------------------------------------- #

class Transaction(BaseModel):
    step:            int   = Field(..., ge=0,  description="Час с начала логирования")
    type:            str   = Field(..., description="Тип транзакции (PAYMENT/TRANSFER/CASH_OUT/DEBIT/CASH_IN)")
    amount:          float = Field(..., ge=0,  description="Сумма")
    nameOrig:        str   = Field(..., description="ID отправителя")
    oldbalanceOrg:   float = Field(..., ge=0)
    newbalanceOrig:  float = Field(..., ge=0)
    nameDest:        str   = Field(..., description="ID получателя")
    oldbalanceDest:  float = Field(..., ge=0)
    newbalanceDest:  float = Field(..., ge=0)


class Prediction(BaseModel):
    is_fraud:    int   = Field(..., description="0 — не мошенничество, 1 — мошенничество")
    probability: float = Field(..., ge=0, le=1, description="Вероятность мошенничества")
    api_version: str   = Field(default=API_VERSION)
    inference_ms: float


# --------------------------------------------------------------------------- #
#  Endpoints
# --------------------------------------------------------------------------- #

@app.get("/health")
def health() -> dict:
    """Liveness/readiness probe."""
    if detector is None:
        raise HTTPException(503, "model not loaded")
    return {"status": "ok"}


@app.get("/version")
def version() -> dict:
    return {"api_version": API_VERSION}


@app.post("/predict", response_model=Prediction)
def predict(tx: Transaction) -> Prediction:
    if detector is None:
        raise HTTPException(503, "model not loaded yet")

    started = time.perf_counter()
    try:
        result = detector.predict(tx.model_dump())
    except Exception as e:
        log.exception("predict failed")
        raise HTTPException(500, f"inference error: {e}")

    return Prediction(
        is_fraud=result["is_fraud"],
        probability=result["probability"],
        inference_ms=(time.perf_counter() - started) * 1000.0,
    )
