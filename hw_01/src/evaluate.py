# Loads the saved model and evaluates on the whole processed dataset (demo).

from __future__ import annotations
import joblib, pandas as pd
from pathlib import Path
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score

DATA = Path("data/processed/train.csv")
MODEL = Path("models/model.pkl")

def main():
    if not (DATA.exists() and MODEL.exists()):
        raise SystemExit("Run data_prep and model_train first.")
    df = pd.read_csv(DATA)
    y = df["is_fraud"]
    X = df.drop(columns=["is_fraud"])
    model = joblib.load(MODEL)
    y_pred = model.predict(X)
    y_proba = model.predict_proba(X)[:,1]
    precision, recall, f1, _ = precision_recall_fscore_support(y, y_pred, average="binary", zero_division=0)
    auc = roc_auc_score(y, y_proba)
    print(f"Precision={precision:.4f} Recall={recall:.4f} F1={f1:.4f} ROC-AUC={auc:.4f}")

if __name__ == "__main__":
    main()