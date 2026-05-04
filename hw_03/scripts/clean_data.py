#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean_data.py — PySpark-скрипт очистки датасета мошеннических финансовых транзакций.

Запуск (внешней системой, например Yandex Data Proc Job):
    spark-submit clean_data.py \
        --input  s3a://<bucket>/raw/ \
        --output s3a://<bucket>/cleaned/fraud_transactions/

Скрипт обнаруживает и обрабатывает следующие типы проблем качества данных:
    1. NULL/пустые значения в ключевых колонках (amount, type, nameOrig, nameDest).
    2. Дубликаты строк.
    3. Невалидные значения: отрицательные суммы, неизвестные категории type,
       отрицательные балансы.
    4. Логическая несогласованность баланса (oldbalanceOrg - newbalanceOrig != amount,
       с учётом допуска).
    5. Некорректные типы данных (приведение типов).

Результат сохраняется в формате parquet (со снэппи-сжатием).
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import List

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, IntegerType, StringType, DoubleType,
)

# ---------------------------------------------------------------------------
# Константы домена
# ---------------------------------------------------------------------------

# Допустимые типы транзакций (PaySim-датасет OTUS)
VALID_TXN_TYPES = ["PAYMENT", "TRANSFER", "CASH_OUT", "DEBIT", "CASH_IN"]

# Ключевые колонки, в которых NULL недопустим
KEY_COLUMNS = ["step", "type", "amount", "nameOrig", "nameDest"]

# Допуск при сравнении балансов (на случай погрешности float)
BALANCE_TOLERANCE = 0.01

# Схема исходного датасета (фиксируем — не доверяем inferSchema)
RAW_SCHEMA = StructType([
    StructField("step",            IntegerType(), True),
    StructField("type",            StringType(),  True),
    StructField("amount",          DoubleType(),  True),
    StructField("nameOrig",        StringType(),  True),
    StructField("oldbalanceOrg",   DoubleType(),  True),
    StructField("newbalanceOrig",  DoubleType(),  True),
    StructField("nameDest",        StringType(),  True),
    StructField("oldbalanceDest",  DoubleType(),  True),
    StructField("newbalanceDest",  DoubleType(),  True),
    StructField("isFraud",         IntegerType(), True),
    StructField("isFlaggedFraud",  IntegerType(), True),
])


# ---------------------------------------------------------------------------
# Логирование
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("clean_data")


# ---------------------------------------------------------------------------
# Аргументы CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cleaning script for fraud transactions dataset")
    p.add_argument("--input",  required=True, help="Input path (s3a://bucket/raw/)")
    p.add_argument("--output", required=True, help="Output path (s3a://bucket/cleaned/fraud_transactions/)")
    p.add_argument("--input-format", default="auto",
                   choices=["auto", "csv", "parquet"],
                   help="Input format. 'auto' = parquet если *.parquet, иначе csv.")
    p.add_argument("--mode", default="overwrite",
                   choices=["overwrite", "append", "errorifexists"])
    return p.parse_args()


# ---------------------------------------------------------------------------
# Spark-сессия
# ---------------------------------------------------------------------------

def build_spark() -> SparkSession:
    return (
        SparkSession.builder
        .appName("MLOpsHW3-CleanFraudData")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.shuffle.partitions", "64")
        .config("spark.sql.parquet.compression.codec", "snappy")
        # Hadoop S3A креды и так подтянутся из конфигурации Data Proc
        .getOrCreate()
    )


# ---------------------------------------------------------------------------
# Чтение
# ---------------------------------------------------------------------------

def read_input(spark: SparkSession, path: str, fmt: str) -> DataFrame:
    if fmt == "auto":
        fmt = "parquet" if path.rstrip("/").endswith(".parquet") or "parquet" in path else "csv"

    log.info("Reading %s as %s", path, fmt)

    if fmt == "csv":
        return (
            spark.read
            .option("header", "true")
            .option("mode", "PERMISSIVE")          # битые строки -> в _corrupt_record
            .option("nullValue", "")
            .schema(RAW_SCHEMA)
            .csv(path)
        )
    return spark.read.parquet(path)


# ---------------------------------------------------------------------------
# Шаги очистки
# ---------------------------------------------------------------------------

def report(df: DataFrame, label: str) -> int:
    n = df.count()
    log.info("[%s] rows: %d", label, n)
    return n


def trim_strings(df: DataFrame, cols: List[str]) -> DataFrame:
    """Срезаем пробелы по краям строковых колонок."""
    for c in cols:
        df = df.withColumn(c, F.trim(F.col(c)))
    return df


def drop_nulls_in_keys(df: DataFrame) -> DataFrame:
    """Проблема №1: NULL в ключевых колонках."""
    return df.dropna(subset=KEY_COLUMNS)


def drop_duplicates(df: DataFrame) -> DataFrame:
    """Проблема №2: полностью дублирующиеся строки."""
    return df.dropDuplicates()


def drop_invalid_values(df: DataFrame) -> DataFrame:
    """Проблема №3: невалидные значения (отрицательные суммы/балансы, неизвестные type)."""
    return df.filter(
        (F.col("amount") >= 0)
        & (F.col("oldbalanceOrg")  >= 0)
        & (F.col("newbalanceOrig") >= 0)
        & (F.col("oldbalanceDest") >= 0)
        & (F.col("newbalanceDest") >= 0)
        & (F.col("type").isin(VALID_TXN_TYPES))
    )


def drop_balance_mismatch(df: DataFrame) -> DataFrame:
    """Проблема №4: нарушение балансового тождества для отправителя.

    Для PAYMENT/TRANSFER/CASH_OUT/DEBIT должно выполняться:
        oldbalanceOrg - newbalanceOrig == amount  (± tolerance)
    Для CASH_IN: newbalanceOrig - oldbalanceOrg == amount.
    Иначе строка считается потенциально битой и удаляется.
    """
    diff_orig = F.col("oldbalanceOrg") - F.col("newbalanceOrig")
    diff_in   = F.col("newbalanceOrig") - F.col("oldbalanceOrg")

    is_outflow = F.col("type").isin(["PAYMENT", "TRANSFER", "CASH_OUT", "DEBIT"])
    is_inflow  = F.col("type") == "CASH_IN"

    valid_outflow = is_outflow & (F.abs(diff_orig - F.col("amount")) <= BALANCE_TOLERANCE)
    valid_inflow  = is_inflow  & (F.abs(diff_in   - F.col("amount")) <= BALANCE_TOLERANCE)

    # Допускаем кейс, когда сторона отправителя — мерчант (M...) и баланс не отслеживается
    merchant_origin = F.col("nameOrig").startswith("M")

    return df.filter(valid_outflow | valid_inflow | merchant_origin)


# ---------------------------------------------------------------------------
# Главный pipeline
# ---------------------------------------------------------------------------

def clean(df: DataFrame) -> DataFrame:
    initial = report(df, "raw")

    df = trim_strings(df, ["type", "nameOrig", "nameDest"])

    df1 = drop_nulls_in_keys(df)
    after_nulls = report(df1, "after_drop_nulls")

    df2 = drop_duplicates(df1)
    after_dups = report(df2, "after_drop_duplicates")

    df3 = drop_invalid_values(df2)
    after_invalid = report(df3, "after_drop_invalid_values")

    df4 = drop_balance_mismatch(df3)
    after_balance = report(df4, "after_drop_balance_mismatch")

    log.info(
        "SUMMARY: raw=%d  -nulls=%d  -dups=%d  -invalid=%d  -balance=%d  ==> kept=%d (%.2f%%)",
        initial,
        initial - after_nulls,
        after_nulls - after_dups,
        after_dups - after_invalid,
        after_invalid - after_balance,
        after_balance,
        100.0 * after_balance / max(initial, 1),
    )
    return df4


def write_output(df: DataFrame, path: str, mode: str) -> None:
    log.info("Writing parquet to %s (mode=%s)", path, mode)
    (
        df.write
        .mode(mode)
        .option("compression", "snappy")
        .parquet(path)
    )
    log.info("Done.")


def main() -> int:
    args = parse_args()
    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    try:
        raw = read_input(spark, args.input, args.input_format)
        cleaned = clean(raw)
        write_output(cleaned, args.output, args.mode)
    except Exception:
        log.exception("Cleaning pipeline failed")
        return 1
    finally:
        spark.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
