#!/bin/bash
# Init-action для Yandex Data Proc 2.1 — ставит MLflow + boto3
# + scikit-learn + statsmodels (нужны для validate_ab.py из hw7).
set -e
sudo /opt/conda/bin/pip install --quiet \
    mlflow==2.16.2 \
    boto3 \
    scikit-learn \
    statsmodels
echo "mlflow + scikit-learn + statsmodels installed:"
/opt/conda/bin/pip show mlflow | grep Version
/opt/conda/bin/pip show statsmodels | grep Version
