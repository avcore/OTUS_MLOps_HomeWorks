# MLOps ДЗ №6 — Регулярное переобучение модели обнаружения мошенничества

Решение домашнего задания №6 курса MLOps от OTUS.

## Архитектура

```
                                +------------------------+
   GitHub repo (DAG, scripts)   |                        |
   ─── (CI/CD) ─────────────►   |   S3 bucket            |
                                |   ├─ dags/             |   ◄─── читает Managed Airflow
                                |   ├─ scripts/          |   ◄─── скачивает Data Proc
                                |   ├─ raw/              |   (исходные данные)
                                |   ├─ cleaned/          |   ◄─── ДЗ №3 положил сюда
                                |   └─ mlflow/           |   ◄─── артефакты моделей
                                +-----------+------------+
                                            ▲
                                            │
       +--------+      +-------+    +-------+--------+    +----------------+
       |Airflow |─────►| DAG   |──► | Data Proc      |───►| MLflow VM      |
       |(MGD)   |      |(*/2h) |    | (временный,    |    | + PostgreSQL   |
       +--------+      +-------+    |  s3-c4-m16 x3) |    |  (cloud-init)  |
                                    +----------------+    +-------+--------+
                                                                  │
                                                                  ▼
                                                        Tracking UI :5000
```

## Что внутри

```
.
├── README.md
├── .gitignore
├── terraform/
│   ├── provider.tf
│   ├── variables.tf
│   ├── main.tf                    # SA + bucket + SG + MLflow VM + Airflow
│   ├── outputs.tf
│   ├── terraform.tfvars.example
│   └── cloud-init/
│       └── mlflow.yaml.tpl        # cloud-init для VM с MLflow + PostgreSQL
├── dags/
│   └── retrain_fraud_model_dag.py # DAG: create DP → train → delete DP
└── scripts/
    └── train_model.py             # PySpark + MLflow + RandomForest
```

## Что сделано (по заданию)

| # | Что требовалось | Где |
|---|---|---|
| 1 | Managed Airflow | `terraform/main.tf` ресурс `yandex_airflow_cluster` |
| 2 | MLflow на отдельной ВМ + БД метаданных | `yandex_compute_instance.mlflow_vm` + cloud-init с PostgreSQL |
| 3 | PySpark скрипт обучения с MLflow | `scripts/train_model.py` |
| 4 | Артефакты модели в S3 | `--default-artifact-root s3://<bucket>/mlflow/` (cloud-init) |
| 5 | Расписание DAG | `schedule="0 */2 * * *"` (каждые 2 часа) |

```
ДЗ №6 выполнено.
Что сделано:
1.  Managed Airflow поднят через Terraform (yandex_airflow_cluster).
2.  MLflow на отдельной ВМ (yandex_compute_instance + cloud-init), БД метаданных
   PostgreSQL установлена на той же VM.
3.  PySpark-скрипт scripts/train_model.py: RandomForestClassifier на очищенных
   данных из ДЗ №3, метрики AUC/F1/recall/precision/accuracy в MLflow.
4.  Артефакты модели сохраняются в S3 (s3://bucket/mlflow/), backend store —
   PostgreSQL на VM.
5.  DAG retrain_fraud_model запускается по расписанию */2h, успешно прошёл
   N запусков. Лучшая модель автоматически промотируется в Production
   (по метрике recall, скрипт сам сравнивает с предыдущей версией).
7.  Все ресурсы удалены через terraform destroy.

Скриншот MLflow с runs: выполнение/
```
