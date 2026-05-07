#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
producer.py — имитатор потока транзакций → Apache Kafka.

Читает parquet с очищенными транзакциями (тот же что в hw3/6),
шлёт записи в Kafka topic `transactions` с заданным RPS.

Запуск как PySpark Job:
    spark-submit producer.py \
        --bootstrap rc1a-...:9091,rc1b-...:9091 \
        --kafka-user mlops-user \
        --kafka-password '...' \
        --topic transactions \
        --input s3a://<bucket>/cleaned/fraud_transactions/ \
        --aws-access-key YCAJ... \
        --aws-secret-key YCP... \
        --rps 50 \
        --duration 60
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("producer")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--bootstrap",      required=True)
    p.add_argument("--kafka-user",     required=True)
    p.add_argument("--kafka-password", required=True)
    p.add_argument("--topic",          default="transactions")
    p.add_argument("--input",          required=True)
    p.add_argument("--aws-access-key", required=True)
    p.add_argument("--aws-secret-key", required=True)
    p.add_argument("--rps",            type=int, default=50,
                   help="Целевой RPS (target messages per second)")
    p.add_argument("--duration",       type=int, default=60,
                   help="Сколько секунд лить трафик")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    os.environ["AWS_ACCESS_KEY_ID"]     = args.aws_access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = args.aws_secret_key

    # ---- ленивые импорты ------------------------------------------------
    import boto3
    import pandas as pd
    from kafka import KafkaProducer

    # ---- 1. Скачиваем parquet локально через boto3 ----------------------
    s3 = boto3.client(
        "s3",
        endpoint_url="https://storage.yandexcloud.net",
        region_name="ru-central1",
    )
    s3_path = args.input.replace("s3a://", "").replace("s3://", "")
    bucket, key = s3_path.split("/", 1)
    key = key.rstrip("/")

    log.info("Listing %s/%s/", bucket, key)
    objs = s3.list_objects_v2(Bucket=bucket, Prefix=key + "/").get("Contents", [])
    pq_keys = [o["Key"] for o in objs if o["Key"].endswith(".parquet")]
    if not pq_keys:
        log.error("No parquet files under s3://%s/%s/", bucket, key)
        return 1

    local_path = "/tmp/source_data.parquet"
    log.info("Downloading %s -> %s", pq_keys[0], local_path)
    s3.download_file(bucket, pq_keys[0], local_path)

    df = pd.read_parquet(local_path)
    log.info("Loaded %d rows from parquet", len(df))

    # ---- 2. Готовим Kafka producer --------------------------------------
    log.info("Connecting to Kafka brokers: %s", args.bootstrap)
    producer = KafkaProducer(
        bootstrap_servers=args.bootstrap.split(","),
        security_protocol="SASL_SSL",
        sasl_mechanism="SCRAM-SHA-512",
        sasl_plain_username=args.kafka_user,
        sasl_plain_password=args.kafka_password,
        ssl_cafile="/etc/ssl/certs/ca-certificates.crt",
        value_serializer=lambda x: json.dumps(x, default=str).encode("utf-8"),
        acks=1,
        linger_ms=10,
        compression_type="gzip",
    )

    # ---- 3. Льём поток с заданным RPS -----------------------------------
    log.info("Sending %d msg/sec for %d seconds = %d total messages",
             args.rps, args.duration, args.rps * args.duration)

    total_sent     = 0
    total_failed   = 0
    start          = time.monotonic()
    n_rows         = len(df)

    for second in range(args.duration):
        sec_start = time.monotonic()

        # Шлём `rps` сообщений за этот один секундный окно
        for i in range(args.rps):
            row_idx = (total_sent + i) % n_rows
            row     = df.iloc[row_idx].to_dict()
            row["_event_ts"] = time.time()
            try:
                producer.send(args.topic, value=row)
            except Exception as e:
                total_failed += 1
                if total_failed < 5:
                    log.warning("send error: %s", e)

        producer.flush()
        total_sent += args.rps

        elapsed_sec = time.monotonic() - sec_start
        if elapsed_sec < 1.0:
            time.sleep(1.0 - elapsed_sec)

        if (second + 1) % 10 == 0 or second == 0:
            log.info("[%2ds/%ds] sent=%d failed=%d (%.1f msg/s actual)",
                     second + 1, args.duration, total_sent, total_failed,
                     args.rps / max(elapsed_sec, 1e-3))

    duration_real = time.monotonic() - start
    log.info("Done. Total sent=%d failed=%d in %.1fs (avg %.1f msg/s)",
             total_sent, total_failed, duration_real, total_sent / duration_real)

    producer.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
