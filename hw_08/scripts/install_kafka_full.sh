#!/bin/bash
# Init-action для Yandex Data Proc 2.1 — ставит mlflow + kafka-python + boto3.
# Spark-Kafka коннектор (jar) подтягивается через --packages в spark-submit.
set -e
sudo /opt/conda/bin/pip install --quiet \
    mlflow==2.16.2 \
    boto3 \
    scikit-learn \
    statsmodels \
    "kafka-python>=2.0,<3.0"
echo "All packages installed:"
/opt/conda/bin/pip show mlflow | grep Version
/opt/conda/bin/pip show kafka-python | grep Version
