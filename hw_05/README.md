# MLOps ДЗ №5 — Apache Airflow для периодической очистки данных

Решение домашнего задания №5 курса MLOps от OTUS.
Поднимаем **Yandex Managed Service for Apache Airflow** через Terraform, кладём DAG в S3, DAG **каждые 30 минут** создаёт временный Spark-кластер, гоняет очистку данных и удаляет кластер.

## Что внутри

```
.
├── README.md
├── .gitignore
├── terraform/
│   ├── provider.tf
│   ├── variables.tf
│   ├── main.tf                  # SA + bucket + SG + yandex_airflow_cluster
│   ├── outputs.tf
│   └── terraform.tfvars.example
├── dags/
│   └── clean_fraud_data_dag.py  # DAG: create → spark-submit → delete
├── scripts/
│   └── clean_data.py            # PySpark скрипт очистки (тот же что в hw3)
├── images/
│   └── airflow_3_runs.png       # СЮДА положите скриншот трёх успешных запусков
└── .github/
    └── workflows/
        └── deploy-dags.yml      # бонус #6: CI/CD синк DAGs в S3
```

## Что сделано (по заданию)

| # | Что требовалось | Где |
|---|---|---|
| 1 | Поднять Managed Airflow | `terraform/main.tf` ресурс `yandex_airflow_cluster` |
| 2 | DAG: создать кластер → spark-submit → удалить | `dags/clean_fraud_data_dag.py` |
| 3 | DAG в репозитории + загружен в Airflow | `dags/` в репо, авто-синк через `code_sync` в S3 |
| 4 | ≥3 успешных запуска по расписанию + скриншот | расписание `*/30 * * * *`, скриншот в `images/airflow_3_runs.png` |
| 6 | CI/CD (бонус) | `.github/workflows/deploy-dags.yml` |
| 7 | Удаление кластера | `terraform destroy` |


```
ДЗ №5 выполнено.

Что сделано:
1.  Yandex Managed Service for Apache Airflow развёрнут через Terraform
   (terraform/main.tf, ресурс yandex_airflow_cluster).
2.  DAG dags/clean_fraud_data_dag.py создаёт временный Data Proc кластер,
   запускает scripts/clean_data.py через spark-submit и удаляет кластер.
3.  DAG загружен в Airflow через S3 code_sync, виден в Web UI.
4.  Расписание */30 * * * *, минимум 3 успешных запуска
   подтверждены скриншотом в README (images/airflow_3_runs.png).
6.  Бонус: CI/CD .github/workflows/deploy-dags.yml — автосинк DAG в S3.
7.  Кластер удалён через terraform destroy.
```
