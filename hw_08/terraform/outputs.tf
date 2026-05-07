output "service_account_id" {
  value = local.sa_id_effective
}

output "bucket_name" {
  value = local.bucket_name_effective
}

output "kafka_cluster_id" {
  value = yandex_mdb_kafka_cluster.this.id
}

output "kafka_bootstrap" {
  description = "Bootstrap servers (host1:9091,host2:9091,...) для SSL подключения"
  value       = join(",", [for h in yandex_mdb_kafka_cluster.this.host : "${h.name}:9091"])
}

output "kafka_user" {
  value = yandex_mdb_kafka_user.user.name
}

output "kafka_password" {
  value     = local.kafka_pass_effective
  sensitive = true
}

output "security_group_id" {
  value = yandex_vpc_security_group.main_sg.id
}

output "airflow_admin_password" {
  value     = var.create_airflow ? local.airflow_admin_pass_effective : "(airflow not created)"
  sensitive = true
}

output "airflow_variables_to_set" {
  value = {
    dp_sa_id        = local.sa_id_effective
    dp_subnet_id    = var.existing_subnet_id
    dp_sg_id        = yandex_vpc_security_group.main_sg.id
    dp_bucket       = local.bucket_name_effective
    dp_zone         = var.yc_zone
    kafka_bootstrap = join(",", [for h in yandex_mdb_kafka_cluster.this.host : "${h.name}:9091"])
    kafka_user      = yandex_mdb_kafka_user.user.name
  }
}
