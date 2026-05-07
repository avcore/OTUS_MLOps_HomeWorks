#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
streaming_inference.py — Spark Structured Streaming с моделью из MLflow.

  Kafka topic `transactions` ──► Spark Streaming ──► model.transform() ──► Kafka topic `predictions`
                                       │
                                       └── модель грузим из MLflow Registry: models:/fraud_detector/Production

Запуск как PySpark Job c пакетом spark-sql-kafka:
    spark-submit \
        --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.0.3 \
        streaming_inference.py \
        --bootstrap rc1a-...:9091 \
        --kafka-user mlops-user \
        --kafka-password '...' \
        --input-topic transactions \
        --output-topic predictions \
        --mlflow-uri http://130.193.37.174:5000 \
        --model-name fraud_detector \
        --aws-access-key YCAJ... \
        --aws-secret-key YCP... \
        --duration 180

После завершения — печатает в лог метрики бенчмарка:
  - input rate (RPS)
  - processed rate (RPS)
  - batch duration
  - сколько сообщений всего обработано
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("stream_infer")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--bootstrap",       required=True)
    p.add_argument("--kafka-user",      required=True)
    p.add_argument("--kafka-password",  required=True)
    p.add_argument("--input-topic",     default="transactions")
    p.add_argument("--output-topic",    default="predictions")
    p.add_argument("--mlflow-uri",      required=True)
    p.add_argument("--model-name",      default="fraud_detector")
    p.add_argument("--aws-access-key",  required=True)
    p.add_argument("--aws-secret-key",  required=True)
    p.add_argument("--duration",        type=int, default=180,
                   help="Сколько секунд работать (timeout)")
    p.add_argument("--starting-offsets", default="latest",
                   choices=["latest", "earliest"])
    return p.parse_args()


def main() -> int:
    args = parse_args()

    os.environ["AWS_ACCESS_KEY_ID"]      = args.aws_access_key
    os.environ["AWS_SECRET_ACCESS_KEY"]  = args.aws_secret_key
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = "https://storage.yandexcloud.net"

    # ---- Spark + MLflow --------------------------------------------------
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    from pyspark.sql.types import (
        StructType, StructField, IntegerType, StringType, DoubleType
    )
    import mlflow
    import mlflow.spark

    spark = (
        SparkSession.builder
        .appName("MLOpsHW8-StreamingInference")
        .config("spark.sql.streaming.checkpointLocation", "/tmp/streaming_chk")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # ---- Загружаем production-модель из MLflow ---------------------------
    mlflow.set_tracking_uri(args.mlflow_uri)
    model_uri = f"models:/{args.model_name}/Production"
    log.info("Loading model from MLflow: %s", model_uri)
    model = mlflow.spark.load_model(model_uri)
    log.info("Model loaded successfully")

    # ---- Схема входных JSON ---------------------------------------------
    schema = StructType([
        StructField("step",            IntegerType()),
        StructField("type",            StringType()),
        StructField("amount",          DoubleType()),
        StructField("nameOrig",        StringType()),
        StructField("oldbalanceOrg",   DoubleType()),
        StructField("newbalanceOrig",  DoubleType()),
        StructField("nameDest",        StringType()),
        StructField("oldbalanceDest",  DoubleType()),
        StructField("newbalanceDest",  DoubleType()),
        StructField("isFraud",         IntegerType()),
        StructField("isFlaggedFraud",  IntegerType()),
        StructField("_event_ts",       DoubleType()),
    ])

    sasl_jaas = (
        'org.apache.kafka.common.security.scram.ScramLoginModule required '
        f'username="{args.kafka_user}" password="{args.kafka_password}";'
    )

    # ---- Чтение из Kafka -------------------------------------------------
    raw = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", args.bootstrap)
        .option("kafka.security.protocol", "SASL_SSL")
        .option("kafka.sasl.mechanism", "SCRAM-SHA-512")
        .option("kafka.sasl.jaas.config", sasl_jaas)
        .option("kafka.ssl.truststore.type", "PEM")
        .option("kafka.ssl.truststore.location", "/etc/ssl/certs/ca-certificates.crt")
        .option("subscribe", args.input_topic)
        .option("startingOffsets", args.starting_offsets)
        .option("maxOffsetsPerTrigger", 5000)
        .load()
    )

    parsed = (
        raw.select(F.from_json(F.col("value").cast("string"), schema).alias("d"))
           .select("d.*")
           .filter(F.col("amount").isNotNull())
    )

    predictions = model.transform(parsed)

    out = predictions.select(
        F.to_json(
            F.struct(
                "step", "type", "amount", "isFraud",
                F.col("prediction").alias("predicted_fraud"),
                F.col("_event_ts").alias("event_ts"),
                (F.unix_timestamp() * 1000).alias("processed_ts_ms"),
            )
        ).alias("value")
    )

    # ---- Запись в Kafka --------------------------------------------------
    query = (
        out.writeStream
        .format("kafka")
        .option("kafka.bootstrap.servers", args.bootstrap)
        .option("kafka.security.protocol", "SASL_SSL")
        .option("kafka.sasl.mechanism", "SCRAM-SHA-512")
        .option("kafka.sasl.jaas.config", sasl_jaas)
        .option("kafka.ssl.truststore.type", "PEM")
        .option("kafka.ssl.truststore.location", "/etc/ssl/certs/ca-certificates.crt")
        .option("topic", args.output_topic)
        .option("checkpointLocation", "/tmp/streaming_chk_" + args.output_topic)
        .trigger(processingTime="5 seconds")
        .start()
    )

    log.info("Streaming started. Will run for %d seconds...", args.duration)

    # ---- Бенчмарк ---------------------------------------------------------
    start = time.monotonic()
    last_log = 0.0
    progress_history = []

    while (time.monotonic() - start) < args.duration:
        time.sleep(5)
        prog = query.lastProgress
        if prog and (time.monotonic() - last_log) >= 5:
            input_rps     = float(prog.get("inputRowsPerSecond")     or 0)
            processed_rps = float(prog.get("processedRowsPerSecond") or 0)
            batch_dur_ms  = float(prog.get("durationMs", {}).get("triggerExecution") or 0)
            num_input     = int(prog.get("numInputRows") or 0)
            log.info("[batch %s] input=%.1f msg/s, processed=%.1f msg/s, "
                     "batch_duration=%.0fms, num_input=%d",
                     prog.get("batchId"), input_rps, processed_rps,
                     batch_dur_ms, num_input)
            progress_history.append({
                "batchId": prog.get("batchId"),
                "input_rps": input_rps,
                "processed_rps": processed_rps,
                "batch_duration_ms": batch_dur_ms,
                "num_input": num_input,
            })
            last_log = time.monotonic()

    log.info("Stopping streaming query...")
    query.stop()

    # ---- Сводка бенчмарка ------------------------------------------------
    if progress_history:
        avg_in   = sum(p["input_rps"]     for p in progress_history) / len(progress_history)
        avg_proc = sum(p["processed_rps"] for p in progress_history) / len(progress_history)
        max_in   = max(p["input_rps"]     for p in progress_history)
        max_proc = max(p["processed_rps"] for p in progress_history)
        total_msg = sum(p["num_input"]    for p in progress_history)

        log.info("=" * 60)
        log.info("BENCHMARK SUMMARY (%d batches over %.0fs):",
                 len(progress_history), time.monotonic() - start)
        log.info("  Avg input rate:      %.1f msg/s", avg_in)
        log.info("  Avg processing rate: %.1f msg/s", avg_proc)
        log.info("  Max input rate:      %.1f msg/s", max_in)
        log.info("  Max processing rate: %.1f msg/s", max_proc)
        log.info("  Total messages:      %d", total_msg)
        log.info("=" * 60)

        if avg_in > avg_proc * 1.05:
            log.warning("Input rate > processing rate by %.1f%% — очередь будет расти",
                        100 * (avg_in - avg_proc) / avg_proc)

    spark.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
