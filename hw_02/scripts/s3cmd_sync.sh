#!/usr/bin/env bash
set -euo pipefail

# Sync source bucket (read-only) to your bucket.
# Requirements:
# 1) s3cmd installed
# 2) ~/.s3cfg configured with your access_key/secret_key and host_base/host_bucket for Yandex Object Storage

if ! command -v s3cmd >/dev/null 2>&1; then
  echo "ERROR: s3cmd is not installed." >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <your_bucket_name>" >&2
  exit 1
fi

SRC="s3://otus-mlops-source-data/"
DST="s3://${1}/"

cat <<MSG
Syncing source dataset into your bucket.
Source:      ${SRC}
Destination: ${DST}
MSG

s3cmd sync \
  --recursive \
  --preserve \
  --no-mime-magic \
  --delete-removed \
  "${SRC}" "${DST}"

echo "Sync complete. Top-level destination listing:"
s3cmd ls "${DST}"
