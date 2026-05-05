output "bucket_name" {
  value = yandex_storage_bucket.main.bucket
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
  value = yandex_vpc_security_group.main_sg.id
}

output "mlflow_vm_public_ip" {
  value = yandex_compute_instance.mlflow_vm.network_interface.0.nat_ip_address
}

output "mlflow_tracking_uri" {
  value = "http://${yandex_compute_instance.mlflow_vm.network_interface.0.nat_ip_address}:5000"
}

output "mlflow_ssh_hint" {
  value = "ssh ubuntu@${yandex_compute_instance.mlflow_vm.network_interface.0.nat_ip_address}"
}

output "airflow_cluster_id" {
  value = yandex_airflow_cluster.this.id
}

output "airflow_admin_login" {
  value = "admin"
}

output "airflow_admin_password" {
  value     = local.airflow_admin_password
  sensitive = true
}

output "airflow_open_ui_hint" {
  value = "Console.yandex.cloud → Managed Service for Apache Airflow → ${yandex_airflow_cluster.this.name} → 'Открыть Apache Airflow'"
}

output "airflow_variables_to_set" {
  value = {
    dp_sa_id            = yandex_iam_service_account.sa.id
    dp_subnet_id        = var.existing_subnet_id
    dp_sg_id            = yandex_vpc_security_group.main_sg.id
    dp_bucket           = yandex_storage_bucket.main.bucket
    dp_zone             = var.yc_zone
    mlflow_tracking_uri = "http://${yandex_compute_instance.mlflow_vm.network_interface.0.nat_ip_address}:5000"
    aws_access_key      = yandex_iam_service_account_static_access_key.sa_static_key.access_key
  }
}
