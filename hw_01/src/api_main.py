from __future__ import annotations
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pathlib import Path
import joblib
import numpy as np

app = FastAPI(title="Fraud Detection API", version="0.1.0")

MODEL_PATH = Path("models/model.pkl")
model = joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None

class InferenceRequest(BaseModel):
    features: list[float]

@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": bool(model)}

@app.post("/predict")
def predict(payload: InferenceRequest):
    if model is None:
        raise HTTPException(503, "Model is not loaded. Train and place models/model.pkl")
    X = np.array([payload.features]).reshape(1, -1)
    proba = float(model.predict_proba(X)[0][1])
    pred = int(proba >= 0.5)
    return {"fraud_probability": proba, "is_fraud": pred}