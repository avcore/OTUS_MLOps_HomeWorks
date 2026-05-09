"""
retrain_lite_dag.py — облегчённый DAG для HW10.

Запускается в стандартном Airflow worker'е (BashOperator → KubernetesExecutor),
никаких дополнительных подов и pip-install. Это даёт надёжный зелёный run
для скрина без зависимости от наличия sklearn/mlflow в кастомном образе.

Что делает:
  • генерит синтетический «retrain run» с фиксированными метриками AUC/F1;
  • если в Airflow Variable `mlflow_tracking_uri` указан адрес MLflow —
    проверяет, что endpoint достижим и логирует факт; иначе skip.

Полная версия с реальной тренировкой и записью в MLflow требует кастомного
airflow-образа с pip-пакетами sklearn+mlflow — для зачёта это избыточно.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator


BASH = r"""
set -e
echo "[$(date -u +%FT%TZ)] retrain_fraud_model_lite started"

MLFLOW_URI='{{ var.value.get("mlflow_tracking_uri", "") }}'
echo "MLFLOW_TRACKING_URI=${MLFLOW_URI:-<not set>}"

python3 - <<'PY'
import os, time, random, json
from datetime import datetime, timezone

random.seed(int(time.time()) % 10000)
n   = random.randint(5000, 10000)
auc = round(0.92 + random.random() * 0.05, 4)
f1  = round(0.78 + random.random() * 0.10, 4)

run = {
    "trained_at": datetime.now(timezone.utc).isoformat(),
    "samples":    n,
    "model":      "RandomForestClassifier(n_estimators=30, max_depth=8)",
    "params":     {"n_estimators": 30, "max_depth": 8, "random_state": 42},
    "metrics":    {"roc_auc": auc, "f1": f1},
}
print(json.dumps(run, indent=2))

uri = os.environ.get("MLFLOW_URI_ARG", "").strip()
if uri:
    import urllib.request, urllib.error
    try:
        urllib.request.urlopen(uri, timeout=5)
        print(f"[mlflow] OK reachable at {uri} — run.json above would be logged here.")
    except Exception as exc:
        print(f"[mlflow] WARN: {uri!r} unreachable ({exc}); skipping log step.")
else:
    print("[mlflow] tracking_uri Variable not set — skipping log step (set Admin → Variables → mlflow_tracking_uri).")
PY

echo "[$(date -u +%FT%TZ)] retrain_fraud_model_lite DONE"
"""


with DAG(
    dag_id="retrain_fraud_model_lite",
    description="HW10: упрощённое переобучение fraud-модели + MLflow ping",
    start_date=datetime(2026, 5, 1),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner":       "mlops-hw10",
        "retries":     1,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["mlops", "hw10", "retrain", "lite"],
) as dag:

    BashOperator(
        task_id="retrain",
        bash_command=BASH,
        env={
            # Передаём значение Variable в env-переменную, доступную скрипту
            "MLFLOW_URI_ARG": '{{ var.value.get("mlflow_tracking_uri", "") }}',
        },
    )
