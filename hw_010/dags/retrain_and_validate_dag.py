"""
retrain_and_validate_dag.py
DAG для регулярной тренировки + A/B валидации модели мошенничества (MLOps ДЗ №7).

Шаги (полный пайплайн hw7):
  1. create_dataproc_cluster — создать временный Spark-кластер
  2. run_train_pyspark_job   — обучить новую challenger-модель
  3. run_validate_ab_job     — провести A/B тест challenger vs champion
  4. delete_dataproc_cluster — удалить кластер (всегда)

Airflow Variables (создавать в Admin → Variables):
    dp_sa_id, dp_subnet_id, dp_sg_id, dp_bucket, dp_zone,
    mlflow_tracking_uri, aws_access_key, aws_secret_key, dp_ssh_pubkey

Внимание: запуск DAG'а требует пакета `apache-airflow-providers-yandex`
(в стандартном image apache/airflow:3.2.0 он не установлен). Если провайдер
отсутствует — DAG корректно регистрируется как **stub** с одной задачей,
которая выводит инструкцию как включить полную версию (через extraPipPackages
helm-chart'а apache-airflow). Так оба DAG'а из hw_010/dags/ остаются видимыми
в UI без ImportError.
"""

from __future__ import annotations

import os as _os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.utils.trigger_rule import TriggerRule

# ---------------------------------------------------------------------------
# Пытаемся импортировать тяжёлый Yandex provider. Если его нет — переходим
# в режим заглушки, чтобы DAG всё равно отображался в Airflow UI.
# ---------------------------------------------------------------------------
try:
    from airflow.providers.yandex.operators.dataproc import (
        DataprocCreateClusterOperator,
        DataprocCreatePysparkJobOperator,
        DataprocDeleteClusterOperator,
    )
    try:
        from yandexcloud._wrappers.dataproc import InitializationAction
    except ImportError:
        from collections import namedtuple
        InitializationAction = namedtuple("InitializationAction", ["uri", "args", "timeout"])

    YANDEX_PROVIDER_AVAILABLE = True
except ImportError:
    YANDEX_PROVIDER_AVAILABLE = False


DAG_ID = "retrain_and_validate_fraud_model"
START_DATE = datetime(2026, 5, 1)


# ===========================================================================
#  ПОЛНАЯ РЕАЛИЗАЦИЯ — выполняется только если apache-airflow-providers-yandex
#  установлен в Airflow.
# ===========================================================================
if YANDEX_PROVIDER_AVAILABLE:

    DP_SA_ID            = Variable.get("dp_sa_id")
    DP_SUBNET_ID        = Variable.get("dp_subnet_id")
    DP_SG_ID            = Variable.get("dp_sg_id")
    DP_BUCKET           = Variable.get("dp_bucket")
    DP_ZONE             = Variable.get("dp_zone", default_var="ru-central1-a")
    DP_SSH_KEY          = Variable.get("dp_ssh_pubkey", default_var="")
    MLFLOW_TRACKING_URI = Variable.get("mlflow_tracking_uri")
    AWS_ACCESS_KEY      = Variable.get("aws_access_key")
    AWS_SECRET_KEY      = Variable.get("aws_secret_key")

    # Уникальное имя кластера (генерируется при парсинге DAG)
    CLUSTER_NAME = "airflow-dp-hw7-" + _os.urandom(4).hex()

    with DAG(
        dag_id=DAG_ID,
        description="Тренировка + A/B валидация модели обнаружения мошенничества (hw7)",
        start_date=START_DATE,
        schedule="0 */3 * * *",
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


# ===========================================================================
#  STUB — если провайдер отсутствует. Сохраняем тот же dag_id, чтобы DAG
#  был виден в UI; одна задача выводит инструкцию.
# ===========================================================================
else:
    from airflow.operators.bash import BashOperator

    INSTALL_NOTE = (
        "Этот DAG из hw_07 (Dataproc + MLflow A/B test) требует "
        "apache-airflow-providers-yandex. В этом Airflow на k8s провайдер "
        "не установлен — DAG отображается как stub. Чтобы включить полную "
        "версию: helm upgrade airflow apache-airflow/airflow ... "
        "--set 'images.airflow.tag=3.2.0-python3.12,extraPipPackages={apache-airflow-providers-yandex==4.0.0}'"
    )

    with DAG(
        dag_id=DAG_ID,
        description="(stub hw_07) полная реализация требует providers-yandex",
        start_date=START_DATE,
        schedule=None,
        catchup=False,
        tags=["mlops", "hw7", "stub"],
    ) as dag:
        BashOperator(
            task_id="info_yandex_provider_missing",
            bash_command=f'echo "{INSTALL_NOTE}"',
        )
