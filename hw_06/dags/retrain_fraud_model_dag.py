"""
retrain_fraud_model_dag.py
Периодическое переобучение модели обнаружения мошенничества (MLOps ДЗ №6).
"""
 
from __future__ import annotations
 
from datetime import datetime, timedelta
 
from airflow import DAG
from airflow.models import Variable
from airflow.providers.yandex.operators.dataproc import (
    DataprocCreateClusterOperator,
    DataprocCreatePysparkJobOperator,
    DataprocDeleteClusterOperator,
)
from airflow.utils.trigger_rule import TriggerRule
 
# Init-action для Data Proc — ставит mlflow на все хосты ПЕРЕД запуском job'а.
try:
    from yandexcloud._wrappers.dataproc import InitializationAction
except ImportError:
    from collections import namedtuple
    InitializationAction = namedtuple("InitializationAction", ["uri", "args", "timeout"])
 
# ---------------------------------------------------------------------------
# Variables
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
 
# Yandex Data Proc принимает имена по regex [a-z][-a-z0-9]{1,61}[a-z0-9]
# В этой версии provider'а cluster_name НЕ в template_fields — Jinja не рендерится.
# Поэтому генерируем имя в момент ПАРСИНГА DAG. Airflow re-парсит DAG раз в ~30 сек,
# так что одно и то же имя живёт максимум полминуты — этого достаточно для уникальности.
import os as _os
CLUSTER_NAME_TPL = "airflow-dp-" + _os.urandom(5).hex()
 
# ---------------------------------------------------------------------------
# DAG
# ---------------------------------------------------------------------------
 
with DAG(
    dag_id="retrain_fraud_model",
    description="Регулярное переобучение модели обнаружения мошенничества",
    start_date=datetime(2026, 5, 1),
    schedule="0 */2 * * *",
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "mlops-hw6",
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["mlops", "hw6", "ml-training", "fraud"],
) as dag:
 
    create_cluster = DataprocCreateClusterOperator(
        task_id="create_dataproc_cluster",
        cluster_name=CLUSTER_NAME_TPL,
        cluster_description="Temporary Data Proc for fraud model training",
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
        # Bootstrap-скрипт ставит mlflow ПЕРЕД запуском job'а
        initialization_actions=[
            InitializationAction(
                uri="s3a://" + DP_BUCKET + "/scripts/install_mlflow.sh",
                args=[],
                timeout=600,
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
 
    delete_cluster = DataprocDeleteClusterOperator(
        task_id="delete_dataproc_cluster",
        trigger_rule=TriggerRule.ALL_DONE,
    )
 
    create_cluster >> train_job >> delete_cluster