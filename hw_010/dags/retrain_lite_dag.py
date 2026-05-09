"""
retrain_lite_dag.py — облегчённый DAG для переобучения fraud-detection
модели прямо внутри Kubernetes кластера (HW10).

В отличие от retrain_and_validate_dag.py (hw7), здесь:
  • не поднимаем Dataproc — обучаемся в одном Python-pod'е через
    KubernetesPodOperator, что бесплатно и быстро (~1 минута);
  • используем тот же образ fraud-api, чтобы переиспользовать train_local.py;
  • логируем метрики в MLflow (URL берём из Airflow Variable mlflow_tracking_uri,
    fallback — env vars).

DAG нужен в первую очередь чтобы:
  1) на скрине Airflow UI видно «retrain_fraud_model_lite» в списке DAG'ов;
  2) можно запустить вручную (Trigger DAG) и увидеть зелёный run;
  3) метрика записывается в MLflow эксперимент `fraud_detection_lite`.

Cron: каждый час. Catchup отключён.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from textwrap import dedent

from airflow import DAG
from airflow.models import Variable
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s


# Тот же образ что у API. CI/CD на main пушит туда же :latest.
# YC_REGISTRY_ID и YC_API_IMAGE можно переопределить через Airflow Variables.
REGISTRY_ID = Variable.get("yc_registry_id", default_var="crpa20hqprok2c48sv5m")
IMAGE       = Variable.get("yc_api_image",   default_var=f"cr.yandex/{REGISTRY_ID}/fraud-api:latest")
MLFLOW_URI  = Variable.get("mlflow_tracking_uri", default_var="")

TRAIN_SCRIPT = dedent(r"""
    set -e
    pip install --quiet mlflow==2.16.2

    python - <<'PY'
    import os, time, joblib, mlflow
    from api.train_local import train_and_save, MODEL_PATH, FEATURE_COLS, generate_synthetic
    from sklearn.metrics import roc_auc_score, f1_score

    uri = os.environ.get("MLFLOW_TRACKING_URI", "").strip()
    if uri:
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment("fraud_detection_lite")

    df = generate_synthetic(n=8000, seed=int(time.time()) % 10000)
    X, y = df[FEATURE_COLS], df["isFraud"]

    train_and_save(MODEL_PATH)
    model = joblib.load(MODEL_PATH)
    proba = model.predict_proba(X)[:, 1]
    auc = float(roc_auc_score(y, proba))
    f1  = float(f1_score(y, (proba > 0.5).astype(int)))

    print(f"AUC={auc:.4f}  F1={f1:.4f}")

    if uri:
        with mlflow.start_run(run_name="retrain_lite_airflow"):
            mlflow.log_params({"n_estimators": 30, "max_depth": 8, "samples": len(df)})
            mlflow.log_metrics({"roc_auc": auc, "f1": f1})
            mlflow.sklearn.log_model(model, "model", registered_model_name="fraud_detector_lite")
        print("MLflow run logged.")
    else:
        print("MLflow URI not set — skipping log_run.")
    PY
""")


with DAG(
    dag_id="retrain_fraud_model_lite",
    description="HW10: переобучение fraud-модели прямо в k8s + MLflow log",
    start_date=datetime(2026, 5, 1),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "mlops-hw10",
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["mlops", "hw10", "retrain", "lite"],
) as dag:

    retrain = KubernetesPodOperator(
        task_id="retrain",
        name="fraud-retrain",
        namespace="airflow",
        image=IMAGE,
        cmds=["bash", "-lc"],
        arguments=[TRAIN_SCRIPT],
        env_vars={"MLFLOW_TRACKING_URI": MLFLOW_URI},
        get_logs=True,
        is_delete_operator_pod=True,
        in_cluster=True,
        # под небольшие requests, чтобы влез на любую ноду
        container_resources=k8s.V1ResourceRequirements(
            requests={"cpu": "200m", "memory": "256Mi"},
            limits={"cpu": "1000m", "memory": "1Gi"},
        ),
    )
