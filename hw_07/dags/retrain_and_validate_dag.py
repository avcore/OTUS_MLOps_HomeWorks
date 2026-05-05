"""
retrain_and_validate_dag.py
DAG для регулярной тренировки + A/B валидации модели мошенничества (MLOps ДЗ №7).

Шаги:
  1. create_dataproc_cluster — создать временный Spark-кластер
  2. run_train_pyspark_job   — обучить новую challenger-модель (тот же скрипт что в hw6)
  3. run_validate_ab_job     — провести A/B тест challenger vs champion (новый шаг hw7)
  4. delete_dataproc_cluster — удалить кластер (всегда)

Airflow Variables (создавать в Admin → Variables):
    dp_sa_id, dp_subnet_id, dp_sg_id, dp_bucket, dp_zone,
    mlflow_tracking_uri, aws_access_key, aws_secret_key, dp_ssh_pubkey
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

# Уникальное имя кластера, генерируем при парсинге DAG (cluster_name не template field)
CLUSTER_NAME = "airflow-dp-hw7-" + _os.urandom(4).hex()

with DAG(
    dag_id="retrain_and_validate_fraud_model",
    description="Тренировка + A/B валидация модели обнаружения мошенничества (hw7)",
    start_date=datetime(2026, 5, 1),
    schedule="0 */3 * * *",   # каждые 3 часа (для теста); в проде @daily
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "mlops-hw7",
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["mlops", "hw7", "ab-test", "fraud", "validation"],
) as dag:

    create_cluster = DataprocCreateClusterOperator(
        task_id="create_dataproc_cluster",
        cluster_name=CLUSTER_NAME,
        cluster_description="Temp Data Proc for retraining + A/B validation",
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
        # На всех хостах ставим mlflow + scikit-learn + statsmodels (для валидации)
        initialization_actions=[
            InitializationAction(
                uri="s3a://" + DP_BUCKET + "/scripts/install_mlflow_full.sh",
                args=[],
                timeout=900,
            )
        ],
        properties={},
    )

    train_job = DataprocCreatePysparkJobOperator(
        task_id="run_train_pyspark_job",
        main_python_file_uri="s3a://" + DP_BUCKET + "/scripts/train_model.py",
        args=[
            "--input=s3a://" + DP_BUCKET + "/cleaned/fraud_transactions/",
            "--mlflow-uri=" + MLFLOW_TRACKING_URI,
            "--experiment=fraud_detection",
            "--aws-access-key=" + AWS_ACCESS_KEY,
            "--aws-secret-key=" + AWS_SECRET_KEY,
            "--num-trees=50",
            "--max-depth=8",
        ],
        properties={
            "spark.submit.deployMode": "client",
            "spark.executorEnv.MLFLOW_S3_ENDPOINT_URL": "https://storage.yandexcloud.net",
            "spark.yarn.appMasterEnv.MLFLOW_S3_ENDPOINT_URL": "https://storage.yandexcloud.net",
        },
    )

    validate_job = DataprocCreatePysparkJobOperator(
        task_id="run_validate_ab_job",
        main_python_file_uri="s3a://" + DP_BUCKET + "/scripts/validate_ab.py",
        args=[
            "--input=s3a://" + DP_BUCKET + "/cleaned/fraud_transactions/",
            "--mlflow-uri=" + MLFLOW_TRACKING_URI,
            "--experiment=fraud_detection",
            "--model-name=fraud_detector",
            "--aws-access-key=" + AWS_ACCESS_KEY,
            "--aws-secret-key=" + AWS_SECRET_KEY,
            "--bootstrap-iter=1000",
            "--alpha=0.05",
        ],
        properties={
            "spark.submit.deployMode": "client",
            "spark.executorEnv.MLFLOW_S3_ENDPOINT_URL": "https://storage.yandexcloud.net",
            "spark.yarn.appMasterEnv.MLFLOW_S3_ENDPOINT_URL": "https://storage.yandexcloud.net",
        },
    )

    delete_cluster = DataprocDeleteClusterOperator(
        task_id="delete_dataproc_cluster",
        trigger_rule=TriggerRule.ALL_DONE,
    )

    create_cluster >> train_job >> validate_job >> delete_cluster
