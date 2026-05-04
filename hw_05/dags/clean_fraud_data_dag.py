"""
clean_fraud_data_dag.py
Периодический запуск процедуры очистки датасета мошеннических финансовых
транзакций по расписанию (MLOps ДЗ №5).

Что делает DAG (3 шага):
    1. Создаёт временный Spark-кластер Yandex Data Processing.
    2. Запускает на нём PySpark-job с нашим скриптом очистки (s3a://.../scripts/clean_data.py).
    3. Удаляет кластер (выполняется ВСЕГДА, даже если шаг 2 упал — trigger_rule=ALL_DONE).

Расписание: каждые 30 минут (для быстрой демонстрации требуемых ≥3 успешных запусков).
Поменять на ежедневное: schedule="@daily".

Перед загрузкой в Airflow убедитесь, что в Airflow Variables (Admin → Variables в UI)
заданы:
    dp_sa_id      = <ID сервисного аккаунта>          (взять из terraform output)
    dp_subnet_id  = <ID подсети с NAT>                (та же, что для Airflow)
    dp_sg_id      = <ID security group>               (та же, что для Airflow)
    dp_bucket     = <имя бакета с DAGs/scripts>
    dp_zone       = ru-central1-a
    dp_ssh_pubkey = "ssh-rsa AAAA..."                 (опционально, для SSH в кластер)
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

# ---------------------------------------------------------------------------
# Чтение Airflow Variables (вынесены наверх, чтобы упасть рано если не заданы)
# ---------------------------------------------------------------------------

DP_SA_ID     = Variable.get("dp_sa_id")
DP_SUBNET_ID = Variable.get("dp_subnet_id")
DP_SG_ID     = Variable.get("dp_sg_id")
DP_BUCKET    = Variable.get("dp_bucket")
DP_ZONE      = Variable.get("dp_zone", default_var="ru-central1-a")
DP_SSH_KEY   = Variable.get("dp_ssh_pubkey", default_var="")

# ---------------------------------------------------------------------------
# Имя кластера — уникальное на каждый запуск (макрос Airflow {{ ts_nodash }})
# ---------------------------------------------------------------------------

CLUSTER_NAME_TPL = "airflow-dp-{{ ts_nodash | lower }}"

# ---------------------------------------------------------------------------
# DAG
# ---------------------------------------------------------------------------

with DAG(
    dag_id="clean_fraud_data",
    description="Периодическая очистка датасета мошеннических транзакций",
    start_date=datetime(2026, 5, 1),
    schedule="*/30 * * * *",     # каждые 30 минут — даст 3 успешных запуска за 1.5 часа
    catchup=False,
    max_active_runs=1,            # одновременно только один запуск (защита от гонок)
    default_args={
        "owner": "mlops-hw5",
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["mlops", "hw5", "fraud-cleaning"],
) as dag:

    # =========================================================================
    # 1) Создание Spark-кластера
    # =========================================================================
    create_cluster = DataprocCreateClusterOperator(
        task_id="create_dataproc_cluster",
        cluster_name=CLUSTER_NAME_TPL,
        cluster_description="Temporary Data Proc cluster for fraud-data cleaning",
        ssh_public_keys=[DP_SSH_KEY] if DP_SSH_KEY else None,
        service_account_id=DP_SA_ID,
        subnet_id=DP_SUBNET_ID,
        security_group_ids=[DP_SG_ID],
        s3_bucket=DP_BUCKET,
        zone=DP_ZONE,
        cluster_image_version="2.1",
        services=["HDFS", "YARN", "SPARK"],

        # Master
        masternode_resource_preset="s3-c2-m8",
        masternode_disk_type="network-hdd",
        masternode_disk_size=40,

        # Data
        datanode_resource_preset="s3-c4-m16",
        datanode_disk_type="network-hdd",
        datanode_disk_size=128,
        datanode_count=2,        # 2 хоста для скорости (можно 3 как в hw3)

        # Compute не нужен
        computenode_count=0,

        # Не пользуемся UI Proxy — экономим время
        # connection_id="yandexcloud_default",  # default подхватится из SA Airflow
    )

    # =========================================================================
    # 2) Запуск нашего скрипта очистки данных
    # =========================================================================
    pyspark_job = DataprocCreatePysparkJobOperator(
        task_id="run_clean_pyspark_job",
        main_python_file_uri=f"s3a://{DP_BUCKET}/scripts/clean_data.py",
        args=[
            f"--input=s3a://{DP_BUCKET}/raw/",
            f"--output=s3a://{DP_BUCKET}/cleaned/fraud_transactions/",
        ],
        properties={
            "spark.submit.deployMode": "cluster",
        },
    )

    # =========================================================================
    # 3) Удаление кластера (всегда — даже если job упал)
    # =========================================================================
    delete_cluster = DataprocDeleteClusterOperator(
        task_id="delete_dataproc_cluster",
        trigger_rule=TriggerRule.ALL_DONE,
    )

    # =========================================================================
    # Порядок выполнения
    # =========================================================================
    create_cluster >> pyspark_job >> delete_cluster
