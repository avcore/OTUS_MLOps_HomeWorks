#!/bin/bash
# Initialization action для Yandex Data Proc 2.1 — ставит mlflow + boto3
# на ВСЕ хосты кластера ПЕРЕД запуском PySpark job'а.
set -e
sudo /opt/conda/bin/pip install --quiet mlflow==2.16.2 boto3
echo "mlflow installed: $(/opt/conda/bin/pip show mlflow | grep Version)"
