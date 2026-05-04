variable "yc_token" {
  description = "Yandex Cloud OAuth token"
  type        = string
  sensitive   = true
}

variable "yc_cloud_id" {
  description = "Yandex Cloud ID"
  type        = string
}

variable "yc_folder_id" {
  description = "Yandex Cloud Folder ID"
  type        = string
}

variable "yc_zone" {
  description = "Default zone (должна совпадать с зоной существующей подсети)"
  type        = string
  default     = "ru-central1-a"
}

variable "bucket_name" {
  description = "Globally unique bucket name для DAGs и скриптов"
  type        = string
}

variable "existing_network_id" {
  description = "ID существующей VPC-сети. Получить: `yc vpc network list`"
  type        = string

  validation {
    condition     = length(var.existing_network_id) > 0
    error_message = "Задайте existing_network_id в terraform.tfvars."
  }
}

variable "existing_subnet_id" {
  description = "ID существующей VPC-подсети. Должна быть в зоне yc_zone и иметь NAT (route_table_id)."
  type        = string

  validation {
    condition     = length(var.existing_subnet_id) > 0
    error_message = "Задайте existing_subnet_id в terraform.tfvars."
  }
}

variable "airflow_admin_password" {
  description = "Пароль администратора Airflow Web UI (логин: admin)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "sa_name" {
  description = "Service account name"
  type        = string
  default     = "mlops-hw5-sa"
}

variable "airflow_cluster_name" {
  description = "Имя Managed Airflow кластера"
  type        = string
  default     = "mlops-hw5-airflow"
}
