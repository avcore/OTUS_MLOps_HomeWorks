output "bucket_name" {
  value = yandex_storage_bucket.data_bucket.bucket
}

output "bucket_endpoint" {
  value = "https://storage.yandexcloud.net/${yandex_storage_bucket.data_bucket.bucket}/"
}

output "service_account_id" {
  value = yandex_iam_service_account.sa.id
}

output "static_access_key" {
  value     = yandex_iam_service_account_static_access_key.sa_static_key.access_key
  sensitive = true
}

output "static_secret_key" {
  value     = yandex_iam_service_account_static_access_key.sa_static_key.secret_key
  sensitive = true
}

output "cluster_id" {
  value = yandex_dataproc_cluster.spark.id
}

output "cluster_name" {
  value = yandex_dataproc_cluster.spark.name
}

output "ui_proxy_hint" {
  value = "Откройте Yandex Cloud Console → Data Proc → ${yandex_dataproc_cluster.spark.name} → UI Proxy → Jupyter"
}
