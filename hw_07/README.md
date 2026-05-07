# MLOps ДЗ №7 — A/B валидация модели обнаружения мошенничества

Решение домашнего задания №7 курса MLOps от OTUS.
Расширяет hw6: к шагу обучения добавляется **шаг A/B валидации** со статистической значимостью (McNemar test + bootstrap CI).

## Что внутри

```
.
├── README.md
├── .gitignore
├── terraform/                              # standalone — копия hw6 на случай если hw6 снесён
│   ├── ...
│   └── cloud-init/mlflow.yaml.tpl
├── dags/
│   └── retrain_and_validate_dag.py         # 4 шага: create → train → validate → delete
└── scripts/
    ├── train_model.py                      # копия из hw6
    ├── validate_ab.py                      # NEW! A/B тест champion vs challenger
    └── install_mlflow_full.sh              # mlflow + scikit-learn + statsmodels
```

## Что сделано (по заданию)

| # | Что требовалось | Где |
|---|---|---|
| 1 | Managed Airflow | reuse hw6 либо `terraform/main.tf` |
| 2 | MLflow на отдельной ВМ + БД метаданных | reuse hw6 либо `terraform/cloud-init/mlflow.yaml.tpl` |
| 3 | **Стратегия валидации + код A/B теста** | `scripts/validate_ab.py` (см. ниже) |
| 4 | Шаг валидации в DAG | `dags/retrain_and_validate_dag.py` (3-й таск `run_validate_ab_job`) |
| 5 | Артефакты модели в S3 | через MLflow `--default-artifact-root s3://...` |
| 6 | Расписание | `schedule="0 */3 * * *"` (каждые 3 часа) |


```
ДЗ №7 выполнено.

Что сделано:
1.  Managed Airflow — переиспользована инфраструктура hw6.
2.  MLflow Tracking Server на VM — переиспользована инфраструктура hw6,
   PostgreSQL для метаданных встроена на ту же VM (cloud-init).
3.  Стратегия валидации:
     - hold-out 20% test set с фикс seed=42
     - сравниваются champion (Production) и challenger (latest)
     - McNemar test на парных предсказаниях (alpha=0.05)
     - Bootstrap 1000 итераций для 95% CI разности recall
   Код: scripts/validate_ab.py
4.  В DAG retrain_and_validate_fraud_model добавлен шаг
   run_validate_ab_job (PySpark job, использует validate_ab.py).
5.  Артефакты валидации (CSV с предсказаниями) и все метрики
   логируются в MLflow → S3 (s3://<bucket>/mlflow/).
6.  Расписание DAG: 0 */3 * * *. Зелёный run подтверждён скриншотом.

Скриншоты: images/airflow_dag_4steps.png, images/mlflow_ab_run.png
```
