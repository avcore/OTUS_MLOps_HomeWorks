#!/usr/bin/env bash
set -euo pipefail

# Run on Data Proc master node.
# Copies from your Object Storage bucket to HDFS using distcp.

if ! command -v hadoop >/dev/null 2>&1; then
  echo "ERROR: hadoop command not found. Run this on the Data Proc master node." >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <your_bucket_name> [hdfs_dir]" >&2
  exit 1
fi

BUCKET="$1"
HDFS_DIR="${2:-/data/otus}"
S3A_SRC="s3a://${BUCKET}/"

cat <<MSG
Preparing HDFS copy.
S3A source: ${S3A_SRC}
HDFS target: ${HDFS_DIR}
MSG

echo "Creating HDFS dir: ${HDFS_DIR}"
hdfs dfs -mkdir -p "${HDFS_DIR}"

echo "Running distcp..."
hadoop distcp \
  -Dfs.s3a.endpoint=storage.yandexcloud.net \
  -Dfs.s3a.path.style.access=true \
  "${S3A_SRC}" "${HDFS_DIR}"

echo "Listing HDFS dir:"
hdfs dfs -ls -h "${HDFS_DIR}"
