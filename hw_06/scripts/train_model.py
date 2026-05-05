#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
train_model.py — обучение модели обнаружения мошеннических транзакций.

Запуск (через Yandex Data Proc PySpark Job):
    spark-submit train_model.py \
        --input s3a://<bucket>/cleaned/fraud_transactions/ \
        --mlflow-uri http://<mlflow-vm-ip>:5000 \
        --experiment fraud_detection \
        --aws-access-key YCAJ... \
        --aws-secret-key YCP... \
        [--limit 200000]   # опционально — для дебага брать только первые N строк

Что делает:
  1. Читает очищенные данные из S3 (parquet).
  2. Делит на train/test (80/20, стратификация по isFraud).
  3. Тренирует RandomForestClassifier (Spark ML).
  4. Считает метрики: AUC, F1, recall (важнее всего для fraud), precision, accuracy.
  5. Сравнивает с предыдущей production-моделью (если есть в MLflow).
  6. Если новая модель лучше по recall — помечает её как production.
  7. Логирует в MLflow: параметры, метрики, артефакт-модель в S3.
"""

from __future__ import annotations

import argparse
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("train_model")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input",            required=True, help="s3a://bucket/cleaned/fraud_transactions/")
    p.add_argument("--mlflow-uri",       required=True, help="http://mlflow-vm:5000")
    p.add_argument("--experiment",       default="fraud_detection")
    p.add_argument("--aws-access-key",   required=True)
    p.add_argument("--aws-secret-key",   required=True)
    p.add_argument("--limit",            type=int, default=0, help="Если >0 — брать только первые N строк")
    p.add_argument("--num-trees",        type=int, default=50)
    p.add_argument("--max-depth",        type=int, default=8)
    return p.parse_args()


def main() -> int:
    args = parse_args()

    # MLflow S3 endpoint (Yandex Object Storage) — должен быть в env ДО импорта mlflow
    os.environ["AWS_ACCESS_KEY_ID"]      = args.aws_access_key
    os.environ["AWS_SECRET_ACCESS_KEY"]  = args.aws_secret_key
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = "https://storage.yandexcloud.net"

    # ---- ленивые импорты, чтобы spark-submit не падал на парсинге ---------
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    from pyspark.ml import Pipeline
    from pyspark.ml.feature import StringIndexer, VectorAssembler
    from pyspark.ml.classification import RandomForestClassifier
    from pyspark.ml.evaluation import (
        BinaryClassificationEvaluator,
        MulticlassClassificationEvaluator,
    )
    import mlflow
    import mlflow.spark

    # ---- Spark -----------------------------------------------------------
    spark = (
        SparkSession.builder
        .appName("MLOpsHW6-FraudTrain")
        .config("spark.sql.adaptive.enabled", "true")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # ---- MLflow ----------------------------------------------------------
    mlflow.set_tracking_uri(args.mlflow_uri)
    mlflow.set_experiment(args.experiment)

    # ---- Чтение данных ---------------------------------------------------
    log.info("Reading cleaned data from %s", args.input)
    df = spark.read.parquet(args.input)
    if args.limit > 0:
        df = df.limit(args.limit)
    df = df.cache()
    n = df.count()
    log.info("Total rows: %d", n)

    # Базовая защита: если данных нет — fail
    if n < 100:
        log.error("Not enough rows in dataset (%d). Aborting.", n)
        spark.stop()
        return 1

    # ---- Подготовка фич --------------------------------------------------
    # Категориальный признак type → индекс
    type_indexer = StringIndexer(
        inputCol="type",
        outputCol="type_idx",
        handleInvalid="keep",
    )

    feature_cols = [
        "step",
        "amount",
        "oldbalanceOrg",
        "newbalanceOrig",
        "oldbalanceDest",
        "newbalanceDest",
        "type_idx",
    ]
    assembler = VectorAssembler(inputCols=feature_cols, outputCol="features", handleInvalid="skip")

    rf = RandomForestClassifier(
        labelCol="isFraud",
        featuresCol="features",
        numTrees=args.num_trees,
        maxDepth=args.max_depth,
        seed=42,
    )

    pipeline = Pipeline(stages=[type_indexer, assembler, rf])

    # ---- Train/Test split ------------------------------------------------
    train, test = df.randomSplit([0.8, 0.2], seed=42)
    log.info("Train: %d, Test: %d", train.count(), test.count())

    # ---- MLflow run ------------------------------------------------------
    with mlflow.start_run() as run:
        run_id = run.info.run_id
        log.info("MLflow run_id=%s", run_id)

        mlflow.log_params({
            "num_trees":   args.num_trees,
            "max_depth":   args.max_depth,
            "rows_total":  n,
            "rows_train":  train.count(),
            "rows_test":   test.count(),
            "features":    ",".join(feature_cols),
            "label":       "isFraud",
            "algorithm":   "RandomForestClassifier",
        })

        log.info("Fitting pipeline...")
        model = pipeline.fit(train)

        log.info("Predicting on test...")
        preds = model.transform(test)

        # ---- Метрики --------------------------------------------------------
        auc_eval = BinaryClassificationEvaluator(
            labelCol="isFraud", rawPredictionCol="rawPrediction", metricName="areaUnderROC"
        )
        f1_eval  = MulticlassClassificationEvaluator(
            labelCol="isFraud", predictionCol="prediction", metricName="f1"
        )
        rec_eval = MulticlassClassificationEvaluator(
            labelCol="isFraud", predictionCol="prediction", metricName="weightedRecall"
        )
        prec_eval = MulticlassClassificationEvaluator(
            labelCol="isFraud", predictionCol="prediction", metricName="weightedPrecision"
        )
        acc_eval = MulticlassClassificationEvaluator(
            labelCol="isFraud", predictionCol="prediction", metricName="accuracy"
        )

        metrics = {
            "auc":       float(auc_eval.evaluate(preds)),
            "f1":        float(f1_eval.evaluate(preds)),
            "recall":    float(rec_eval.evaluate(preds)),
            "precision": float(prec_eval.evaluate(preds)),
            "accuracy":  float(acc_eval.evaluate(preds)),
        }
        log.info("Metrics: %s", metrics)
        mlflow.log_metrics(metrics)

        # ---- Логируем артефакт-модель в S3 ----------------------------------
        log.info("Logging Spark model to MLflow (S3 artifact root)...")
        mlflow.spark.log_model(
            spark_model=model,
            artifact_path="model",
            registered_model_name="fraud_detector",
        )

        # ---- Регистрация и продвижение в production -------------------------
        client = mlflow.tracking.MlflowClient()
        # последняя только что зарегистрированная версия
        latest = client.get_latest_versions("fraud_detector", stages=["None"])[-1]
        new_version = latest.version
        log.info("Registered fraud_detector v%s", new_version)

        # сравним с текущей Production
        try:
            prod_versions = client.get_latest_versions("fraud_detector", stages=["Production"])
        except Exception:
            prod_versions = []

        if not prod_versions:
            log.info("No Production model yet — promoting new model to Production")
            client.transition_model_version_stage(
                name="fraud_detector",
                version=new_version,
                stage="Production",
                archive_existing_versions=True,
            )
        else:
            prod = prod_versions[0]
            prod_run = client.get_run(prod.run_id)
            prod_recall = prod_run.data.metrics.get("recall", 0.0)
            log.info("Current Production recall=%.4f, new=%.4f", prod_recall, metrics["recall"])

            if metrics["recall"] > prod_recall:
                log.info("New model BETTER → promoting v%s to Production", new_version)
                client.transition_model_version_stage(
                    name="fraud_detector",
                    version=new_version,
                    stage="Production",
                    archive_existing_versions=True,
                )
            else:
                log.info("New model worse — leaving Production as-is, marking new as Archived")
                client.transition_model_version_stage(
                    name="fraud_detector",
                    version=new_version,
                    stage="Archived",
                )

    log.info("Training run finished.")
    spark.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
