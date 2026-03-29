output "bucket_name" {
  value = yandex_storage_bucket.target.bucket
}

output "bucket_endpoint" {
  value = "https://storage.yandexcloud.net/${yandex_storage_bucket.target.bucket}"
}

output "s3_access_key" {
  value     = yandex_iam_service_account_static_access_key.sa_key.access_key
  sensitive = true
}

output "s3_secret_key" {
  value     = yandex_iam_service_account_static_access_key.sa_key.secret_key
  sensitive = true
}

output "dataproc_cluster_id" {
  value = yandex_dataproc_cluster.this.id
}

output "public_bucket_url" {
  description = "Shareable bucket URL for homework review when public_bucket_read=true."
  value       = var.public_bucket_read ? "https://storage.yandexcloud.net/${yandex_storage_bucket.target.bucket}/" : null
}

output "estimated_cluster_hourly_usd" {
  description = "Approximate hourly cluster cost in USD"
  value       = local.cluster_hourly_estimate
}

output "estimated_cluster_monthly_usd" {
  description = "Approximate monthly cluster cost in USD"
  value       = local.cluster_monthly_estimate
}

output "estimated_hdfs_storage_monthly_usd" {
  description = "Approximate monthly HDFS storage cost in USD"
  value       = local.hdfs_monthly_storage_estimate
}

output "estimated_object_storage_monthly_usd" {
  description = "Approximate monthly Object Storage cost in USD"
  value       = local.object_storage_monthly_estimate
}

output "estimated_hdfs_to_object_storage_ratio" {
  description = "Approximate ratio of HDFS storage cost to Object Storage cost"
  value       = local.hdfs_vs_object_storage_ratio
}
