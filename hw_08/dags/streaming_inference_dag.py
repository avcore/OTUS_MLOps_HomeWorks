"""
streaming_inference_dag.py
DAG для Kafka-стриминга и бенчмарка модели (MLOps ДЗ №8).

Шаги:
  1. create_dataproc_cluster — создать временный Spark-кластер с init-action
  2. start_streaming_inference — Spark Structured Streaming consumer
                                 (читает Kafka, применяет модель, пишет в predictions)
                                 — запускается ПЕРВЫМ и ждёт producer-а
  3. run_producer              — Kafka producer (генерирует поток с заданным RPS)
                                 — запускается ВТОРЫМ параллельно
  4. delete_dataproc_cluster   — удалить кластер (всегда)

Параллельный запуск streaming + producer достигается через TaskGroup
с trigger_rule=ALL_DONE на delete и общим upstream'ом create_cluster.

Airflow Variables (в дополнение к hw6/7 переменным):
  kafka_bootstrap   — host1:9091,host2:9091
  kafka_user        — mlops-user
  kafka_password    — пароль (mark Sensitive!)
  benchmark_rps     — 50 (или 100, 200, 400 — для разных тестов)
  benchmark_duration — 120 (секунды)
"""

from __future__ import annotations

import os as _os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.providers.yandex.operators.dataproc import (
    DataprocCreateClusterOperator,
    DataprocCreatePysparkJobOperator,
    DataprocDeleteClusterOperator,
)
from airflow.utils.trigger_rule import TriggerRule

try:
    from yandexcloud._wrappers.dataproc import InitializationAction
except ImportError:
    from collections import namedtuple
    InitializationAction = namedtuple("InitializationAction", ["uri", "args", "timeout"])

# ---------------------------------------------------------------------------
DP_SA_ID            = Variable.get("dp_sa_id")
DP_SUBNET_ID        = Variable.get("dp_subnet_id")
DP_SG_ID            = Variable.get("dp_sg_id")
DP_BUCKET           = Variable.get("dp_bucket")
DP_ZONE             = Variable.get("dp_zone", default_var="ru-central1-a")
DP_SSH_KEY          = Variable.get("dp_ssh_pubkey", default_var="")
MLFLOW_TRACKING_URI = Variable.get("mlflow_tracking_uri")
AWS_ACCESS_KEY      = Variable.get("aws_access_key")
AWS_SECRET_KEY      = Variable.get("aws_secret_key")

KAFKA_BOOTSTRAP    = Variable.get("kafka_bootstrap")
KAFKA_USER         = Variable.get("kafka_user", default_var="mlops-user")
KAFKA_PASSWORD     = Variable.get("kafka_password")
BENCHMARK_RPS      = Variable.get("benchmark_rps", default_var="50")
BENCHMARK_DURATION = Variable.get("benchmark_duration", default_var="120")

CLUSTER_NAME = "airflow-dp-hw8-" + _os.urandom(4).hex()

# Spark-Kafka коннектор. Версия должна совпадать с версией Spark в Data Proc 2.1.
SPARK_KAFKA_PACKAGE = "org.apache.spark:spark-sql-kafka-0-10_2.12:3.0.3"

with DAG(
    dag_id="streaming_inference_benchmark",
    description="Kafka streaming inference + RPS бенчмарк (hw8)",
    start_date=datetime(2026, 5, 1),
    schedule=None,            # ручной запуск; для регулярки можно "@daily"
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "mlops-hw8",
        "retries": 0,         # для бенчмарка retry не нужен
    },
    tags=["mlops", "hw8", "kafka", "streaming", "benchmark"],
) as dag:

    # =========================================================================
    # 1) Создание Spark-кластера с init-action (mlflow + kafka-python + ...)
    # =========================================================================
    create_cluster = DataprocCreateClusterOperator(
        task_id="create_dataproc_cluster",
        cluster_name=CLUSTER_NAME,
        cluster_description="Streaming inference + Kafka benchmark",
        ssh_public_keys=[DP_SSH_KEY] if DP_SSH_KEY else None,
        service_account_id=DP_SA_ID,
        subnet_id=DP_SUBNET_ID,
        security_group_ids=[DP_SG_ID],
        s3_bucket=DP_BUCKET,
        zone=DP_ZONE,
        cluster_image_version="2.1",
        services=["HDFS", "YARN", "SPARK"],
        masternode_resource_preset="s3-c4-m16",
        masternode_disk_type="network-hdd",
        masternode_disk_size=40,
        datanode_resource_preset="s3-c4-m16",
        datanode_disk_type="network-hdd",
        datanode_disk_size=128,
        datanode_count=2,
        computenode_count=0,
        initialization_actions=[
            InitializationAction(
                uri="s3a://" + DP_BUCKET + "/scripts/install_kafka_full.sh",
                args=[],
                timeout=900,
            )
        ],
        properties={},
    )

    # =========================================================================
    # 2) Streaming inference (читает Kafka, применяет модель, пишет результат)
    # =========================================================================
    streaming_job = DataprocCreatePysparkJobOperator(
        task_id="run_streaming_inference",
        main_python_file_uri="s3a://" + DP_BUCKET + "/scripts/streaming_inference.py",
        args=[
            "--bootstrap=" + KAFKA_BOOTSTRAP,
            "--kafka-user=" + KAFKA_USER,
            "--kafka-password=" + KAFKA_PASSWORD,
            "--input-topic=transactions",
            "--output-topic=predictions",
            "--mlflow-uri=" + MLFLOW_TRACKING_URI,
            "--model-name=fraud_detector",
            "--aws-access-key=" + AWS_ACCESS_KEY,
            "--aws-secret-key=" + AWS_SECRET_KEY,
            "--duration=" + str(int(BENCHMARK_DURATION) + 30),  # +30s запаса
            "--starting-offsets=latest",
        ],
        packages=[SPARK_KAFKA_PACKAGE],
        properties={
            "spark.submit.deployMode": "client",
            "spark.executorEnv.MLFLOW_S3_ENDPOINT_URL": "https://storage.yandexcloud.net",
            "spark.yarn.appMasterEnv.MLFLOW_S3_ENDPOINT_URL": "https://storage.yandexcloud.net",
        },
    )

    # =========================================================================
    # 3) Producer (генератор потока в Kafka) — параллельно со streaming
    # =========================================================================
    producer_job = DataprocCreatePysparkJobOperator(
        task_id="run_producer",
        main_python_file_uri="s3a://" + DP_BUCKET + "/scripts/producer.py",
        args=[
            "--bootstrap=" + KAFKA_BOOTSTRAP,
            "--kafka-user=" + KAFKA_USER,
            "--kafka-password=" + KAFKA_PASSWORD,
            "--topic=transactions",
            "--input=s3a://" + DP_BUCKET + "/cleaned/fraud_transactions/",
            "--aws-access-key=" + AWS_ACCESS_KEY,
            "--aws-secret-key=" + AWS_SECRET_KEY,
            "--rps=" + BENCHMARK_RPS,
            "--duration=" + BENCHMARK_DURATION,
        ],
        properties={"spark.submit.deployMode": "client"},
    )

    # =========================================================================
    # 4) Удаление кластера (всегда)
    # =========================================================================
    delete_cluster = DataprocDeleteClusterOperator(
        task_id="delete_dataproc_cluster",
        trigger_rule=TriggerRule.ALL_DONE,
    )

    # =========================================================================
    # Граф: create → [streaming, producer] → delete
    # streaming и producer стартуют почти одновременно (Spark Job
    # асинхронный — Airflow не ждёт окончания одного перед стартом другого
    # внутри parallel-группы)
    # =========================================================================
    create_cluster >> [streaming_job, producer_job] >> delete_cluster
