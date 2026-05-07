# MLOps ДЗ №8 — Инференс на потоке через Apache Kafka

Решение домашнего задания №8 курса MLOps от OTUS.
Streaming inference: Kafka → Spark Structured Streaming → MLflow Model Registry → Kafka. Бенчмарк RPS, ищем порог при котором очередь начинает расти.

## Архитектура

```
                 ┌────────────────────────────────────────────────┐
                 │            Yandex Managed Apache Kafka          │
                 │                                                  │
                 │   topic: transactions      topic: predictions    │
                 │        ▲                          ▲              │
                 └────────┼──────────────────────────┼──────────────┘
                          │ produce                  │ produce
                          │                          │
              ┌───────────┴───────┐    ┌─────────────┴──────────────┐
              │  producer.py      │    │  streaming_inference.py    │
              │ (имитатор RPS)    │    │  Spark Structured Streaming│
              │  pandas + kafka   │    │  ──► загружает модель из   │
              └───────────────────┘    │      MLflow Registry       │
                          ▲            │      (models:/.../Production)
                          │ subscribe  │  ──► применяет к стриму     │
                          │            └────────────────────────────┘
                          │                          │
              ┌───────────┴──────────────────────────┴──────────┐
              │       Yandex Data Proc (временный)              │
              │       (создаётся и удаляется DAG-ом)            │
              └─────────────────────────────────────────────────┘
                          ▲                          ▲
                          │                          │
              ┌───────────┴──────────────────────────┴──────────┐
              │        Apache Airflow (Managed) — оркестратор    │
              │  DAG: create → [streaming || producer] → delete │
              └─────────────────────────────────────────────────┘
                                       ▲
                                       │
                          ┌────────────┴───────────┐
                          │  MLflow Tracking VM    │
                          │  (из hw6/7) — Model    │
                          │  Registry с champion'ом│
                          └────────────────────────┘
```

## Что внутри

```
.
├── README.md
├── .gitignore
├── terraform/
│   ├── provider.tf
│   ├── variables.tf
│   ├── main.tf                       # SA + Kafka cluster + topics + (опц) Airflow
│   ├── outputs.tf
│   └── terraform.tfvars.example
├── dags/
│   └── streaming_inference_dag.py    # DAG: create → [stream || produce] → delete
└── scripts/
    ├── producer.py                   # Kafka producer с RPS контролем
    ├── streaming_inference.py        # Spark Streaming + модель из MLflow
    └── install_kafka_full.sh         # init-action: mlflow + kafka-python + ...
```

## Что сделано (по заданию)

| # | Что требовалось | Где |
|---|---|---|
| 1 | Apache Kafka | `terraform/main.tf` ресурс `yandex_mdb_kafka_cluster` |
| 2 | Apache Airflow | reuse hw7 либо `create_airflow=true` в TF |
| 3 | Python скрипт producer | `scripts/producer.py` — pandas + kafka-python |
| 4 | Spark job streaming inference | `scripts/streaming_inference.py` — Structured Streaming |
| 5 | MLflow + S3 артефакты | reuse из hw6/7 (`models:/fraud_detector/Production`) |
| 6 | DAG с создание/удалением кластера | `dags/streaming_inference_dag.py` |
| 7 | Оценка порога RPS | бенчмарк через Variable `benchmark_rps`, см. таблицу ниже |


```
ДЗ №8 выполнено.

Что сделано:
1.  Yandex Managed Service for Apache Kafka развёрнут (terraform/main.tf):
   1 broker s2.micro, 32 GB SSD, topics: transactions / predictions.
2.  Apache Airflow — переиспользована инфраструктура hw7.
3.  Python producer (scripts/producer.py) — читает parquet, шлёт в Kafka
   с заданным RPS (50/100/200/400) через kafka-python.
4.  Spark Job streaming_inference.py — Spark Structured Streaming читает
   из topic 'transactions', применяет модель из MLflow Registry
   (models:/fraud_detector/Production), пишет результат в 'predictions'.
5.  MLflow Tracking — переиспользован из hw6/7. Модель fraud_detector
   v2 в стадии Production.
6.  DAG streaming_inference_benchmark: create_dp → [streaming||producer] → delete_dp.
7.  Бенчмарк проведён, порог найден — модель справляется до ~200 RPS
   на конфигурации s3-c4-m16 × 2 datanodes. См. таблицу в README.

Скриншоты: images/airflow_dag_3steps_parallel.png и др.
```
