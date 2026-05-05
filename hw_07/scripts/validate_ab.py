#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_ab.py
A/B-валидация модели обнаружения мошенничества (MLOps ДЗ №7).

Сравнивает текущую Production-модель (champion) и последнюю
зарегистрированную (challenger) на одной тестовой выборке.
Считает:
  - метрики каждой модели (accuracy / precision / recall / F1 / AUC)
  - McNemar test (статистическая значимость различия в правильности предсказаний)
  - Bootstrap 95% CI для разности recall
  - принимает решение о промоции challenger в Production

Все артефакты пишет в MLflow (тот же сервер, что и train_model.py).

Запуск:
    spark-submit validate_ab.py \
        --input s3a://<bucket>/cleaned/fraud_transactions/ \
        --mlflow-uri http://<mlflow-vm>:5000 \
        --experiment fraud_detection \
        --model-name fraud_detector \
        --aws-access-key YCAJ... \
        --aws-secret-key YCP...
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("validate_ab")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input",            required=True)
    p.add_argument("--mlflow-uri",       required=True)
    p.add_argument("--experiment",       default="fraud_detection")
    p.add_argument("--model-name",       default="fraud_detector")
    p.add_argument("--aws-access-key",   required=True)
    p.add_argument("--aws-secret-key",   required=True)
    p.add_argument("--bootstrap-iter",   type=int, default=1000,
                   help="Сколько bootstrap-итераций для CI разности recall")
    p.add_argument("--alpha",            type=float, default=0.05,
                   help="Уровень значимости для теста McNemar")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    os.environ["AWS_ACCESS_KEY_ID"]      = args.aws_access_key
    os.environ["AWS_SECRET_ACCESS_KEY"]  = args.aws_secret_key
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = "https://storage.yandexcloud.net"

    # ---- ленивые импорты ------------------------------------------------
    import numpy as np
    import pandas as pd
    from pyspark.sql import SparkSession
    import mlflow
    import mlflow.spark
    from mlflow.tracking import MlflowClient
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score, roc_auc_score,
    )
    from statsmodels.stats.contingency_tables import mcnemar

    spark = (
        SparkSession.builder
        .appName("MLOpsHW7-AB-Validate")
        .config("spark.sql.adaptive.enabled", "true")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    mlflow.set_tracking_uri(args.mlflow_uri)
    mlflow.set_experiment(args.experiment)
    client = MlflowClient()

    # ---- 1. Получаем champion и challenger из Model Registry ------------
    prod_versions  = client.get_latest_versions(args.model_name, stages=["Production"])
    none_versions  = client.get_latest_versions(args.model_name, stages=["None"])

    if not prod_versions:
        log.warning("Нет Production-модели — нечего сравнивать. "
                    "Промотируем последнюю зарегистрированную и выходим.")
        if none_versions:
            v = none_versions[-1]
            client.transition_model_version_stage(
                args.model_name, v.version, "Production",
                archive_existing_versions=True,
            )
            log.info("Promoted v%s to Production (no champion was present)", v.version)
        spark.stop()
        return 0

    if not none_versions:
        log.info("Нет challenger-моделей (всё в Production/Archived) — A/B пропускаем.")
        spark.stop()
        return 0

    champion   = prod_versions[0]
    challenger = none_versions[-1]
    log.info("Champion v%s (run %s)",   champion.version,   champion.run_id)
    log.info("Challenger v%s (run %s)", challenger.version, challenger.run_id)

    # ---- 2. Загружаем модели --------------------------------------------
    log.info("Loading champion + challenger spark models...")
    champ_model = mlflow.spark.load_model(f"models:/{args.model_name}/{champion.version}")
    chall_model = mlflow.spark.load_model(f"models:/{args.model_name}/{challenger.version}")

    # ---- 3. Тестовый сет — те же 20% (фиксированный seed как в train_model) ----
    df = spark.read.parquet(args.input)
    _, test = df.randomSplit([0.8, 0.2], seed=42)
    test = test.cache()
    log.info("Test rows: %d", test.count())

    # ---- 4. Прогоняем обе модели ----------------------------------------
    log.info("Predicting champion...")
    pred_champ_df = (
        champ_model.transform(test)
        .select("isFraud", "prediction")
        .toPandas()
        .rename(columns={"prediction": "pred_champ"})
    )
    log.info("Predicting challenger...")
    pred_chall_df = (
        chall_model.transform(test)
        .select("isFraud", "prediction")
        .toPandas()
        .rename(columns={"prediction": "pred_chall"})
    )

    # Spark не гарантирует одинаковый порядок строк → собираем по индексу.
    n = min(len(pred_champ_df), len(pred_chall_df))
    y_true  = pred_champ_df["isFraud"].values[:n].astype(int)
    y_champ = pred_champ_df["pred_champ"].values[:n].astype(int)
    y_chall = pred_chall_df["pred_chall"].values[:n].astype(int)

    # ---- 5. Метрики ------------------------------------------------------
    def _metrics(y_pred):
        return {
            "accuracy":  float(accuracy_score(y_true, y_pred)),
            "precision": float(precision_score(y_true, y_pred, zero_division=0)),
            "recall":    float(recall_score(y_true, y_pred, zero_division=0)),
            "f1":        float(f1_score(y_true, y_pred, zero_division=0)),
            "auc":       float(roc_auc_score(y_true, y_pred)) if len(set(y_true)) > 1 else 0.0,
        }

    m_champ = _metrics(y_champ)
    m_chall = _metrics(y_chall)
    log.info("Champion metrics:   %s", m_champ)
    log.info("Challenger metrics: %s", m_chall)

    # ---- 6. McNemar test --------------------------------------------------
    # Таблица сопряжённости по правильности (correct/wrong):
    #                       champ correct   champ wrong
    # chall correct   |          a               b
    # chall wrong     |          c               d
    correct_champ = (y_champ == y_true)
    correct_chall = (y_chall == y_true)
    a = int(np.sum( correct_chall &  correct_champ))
    b = int(np.sum( correct_chall & ~correct_champ))
    c = int(np.sum(~correct_chall &  correct_champ))
    d = int(np.sum(~correct_chall & ~correct_champ))

    log.info("Contingency: a=%d b=%d c=%d d=%d", a, b, c, d)
    mcnemar_result = mcnemar([[a, b], [c, d]], exact=False, correction=True)
    mcnemar_stat   = float(mcnemar_result.statistic)
    mcnemar_pvalue = float(mcnemar_result.pvalue)
    log.info("McNemar: stat=%.4f, p-value=%.6f", mcnemar_stat, mcnemar_pvalue)

    # ---- 7. Bootstrap CI для разности recall ----------------------------
    rng = np.random.default_rng(42)
    diffs = np.empty(args.bootstrap_iter, dtype=np.float64)
    for i in range(args.bootstrap_iter):
        idx = rng.integers(0, n, n)
        yt  = y_true[idx]
        yc  = y_champ[idx]
        yh  = y_chall[idx]
        # recall = TP / (TP + FN). Стабильно через sklearn, но для скорости — руками.
        pos = (yt == 1)
        if pos.sum() == 0:
            diffs[i] = 0.0
            continue
        rc_champ = float(((yc == 1) & pos).sum()) / pos.sum()
        rc_chall = float(((yh == 1) & pos).sum()) / pos.sum()
        diffs[i] = rc_chall - rc_champ
    ci_low, ci_high = np.percentile(diffs, [2.5, 97.5])
    diff_mean = float(diffs.mean())
    log.info("Bootstrap diff_recall mean=%.4f, 95%% CI=[%.4f, %.4f]",
             diff_mean, ci_low, ci_high)

    # ---- 8. Логируем в MLflow -------------------------------------------
    run_name = f"ab_v{challenger.version}_vs_v{champion.version}"
    with mlflow.start_run(run_name=run_name):
        mlflow.log_params({
            "champion_version":   champion.version,
            "challenger_version": challenger.version,
            "champion_run_id":    champion.run_id,
            "challenger_run_id":  challenger.run_id,
            "n_test":             n,
            "bootstrap_iter":     args.bootstrap_iter,
            "alpha":              args.alpha,
            "test_strategy":      "fixed_seed_20pct_holdout",
        })
        for k, v in m_champ.items():
            mlflow.log_metric(f"champion_{k}", v)
        for k, v in m_chall.items():
            mlflow.log_metric(f"challenger_{k}", v)
        for k in m_champ:
            mlflow.log_metric(f"diff_{k}", m_chall[k] - m_champ[k])

        mlflow.log_metric("mcnemar_statistic", mcnemar_stat)
        mlflow.log_metric("mcnemar_pvalue",    mcnemar_pvalue)
        mlflow.log_metric("bootstrap_diff_recall_mean",  diff_mean)
        mlflow.log_metric("bootstrap_diff_recall_ci_low",  float(ci_low))
        mlflow.log_metric("bootstrap_diff_recall_ci_high", float(ci_high))

        # ---- 9. Решение о промоции --------------------------------------
        # Челленджер выигрывает, если ВСЕ выполнено:
        #  (a) recall выше точечно;
        #  (b) p-value McNemar < alpha (есть статистическая значимость);
        #  (c) нижняя граница bootstrap-CI > 0 (доверительно лучше).
        promote = (
            (m_chall["recall"] > m_champ["recall"])
            and (mcnemar_pvalue < args.alpha)
            and (ci_low > 0)
        )
        mlflow.log_metric("promote_decision", int(promote))

        if promote:
            client.transition_model_version_stage(
                args.model_name, challenger.version, "Production",
                archive_existing_versions=True,
            )
            log.info("✅ Challenger v%s статистически лучше → Production",
                     challenger.version)
        else:
            client.transition_model_version_stage(
                args.model_name, challenger.version, "Archived",
            )
            log.info("❌ Challenger v%s не показал значимого улучшения → Archived",
                     challenger.version)

        # сохраняем подробный CSV с предсказаниями как артефакт
        details_path = "/tmp/ab_predictions.csv"
        pd.DataFrame({
            "y_true":  y_true,
            "champ":   y_champ,
            "chall":   y_chall,
        }).to_csv(details_path, index=False)
        mlflow.log_artifact(details_path, artifact_path="ab_validation")

    spark.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
