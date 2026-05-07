# Trains a baseline model on `data/processed/train.csv` and saves to `models/model.pkl`.

from __future__ import annotations
import os, joblib
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.linear_model import LogisticRegression

DATA = Path("data/processed/train.csv")
MODEL_OUT = Path("models/model.pkl")

def main():
    if not DATA.exists():
        raise SystemExit("Processed data not found. Run `python -m src.data_prep` first.")
    df = pd.read_csv(DATA)
    y = df["is_fraud"]
    X = df.drop(columns=["is_fraud"])
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, stratify=y, random_state=42)

    pipe = Pipeline([
        ("scaler", StandardScaler(with_mean=False)),  # robust on sparse-like
        ("clf", LogisticRegression(max_iter=200, class_weight="balanced"))
    ])
    pipe.fit(X_train, y_train)
    preds = pipe.predict(X_test)
    proba = pipe.predict_proba(X_test)[:,1]
    print(classification_report(y_test, preds, digits=4))
    print("ROC-AUC:", roc_auc_score(y_test, proba))

    os.makedirs(MODEL_OUT.parent, exist_ok=True)
    joblib.dump(pipe, MODEL_OUT)
    print(f"[model_train] saved model to {MODEL_OUT}")

if __name__ == "__main__":
    main()