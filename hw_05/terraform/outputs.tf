output "bucket_name" {
  value = yandex_storage_bucket.airflow_bucket.bucket
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

output "security_group_id" {
  value = yandex_vpc_security_group.airflow_sg.id
}

output "airflow_cluster_id" {
  value = yandex_airflow_cluster.this.id
}

output "airflow_open_ui_hint" {
  value = "Console.yandex.cloud → Managed Service for Apache Airflow → ${yandex_airflow_cluster.this.name} → кнопка 'Открыть Apache Airflow'"
}

output "airflow_admin_login" {
  value = "admin"
}

output "airflow_admin_password" {
  value     = local.airflow_admin_password
  sensitive = true
}

# Эти значения нужно будет проставить как Airflow Variables (см. README)
output "airflow_variables_to_set" {
  value = {
    dp_sa_id     = yandex_iam_service_account.sa.id
    dp_subnet_id = var.existing_subnet_id
    dp_sg_id     = yandex_vpc_security_group.airflow_sg.id
    dp_bucket    = yandex_storage_bucket.airflow_bucket.bucket
    dp_zone      = var.yc_zone
  }
}
