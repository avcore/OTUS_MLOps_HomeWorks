variable "yc_token" {
  type      = string
  sensitive = true
}

variable "yc_cloud_id" {
  type = string
}

variable "yc_folder_id" {
  type = string
}

variable "yc_zone" {
  type    = string
  default = "ru-central1-a"
}

variable "existing_network_id" {
  type = string
  validation {
    condition     = length(var.existing_network_id) > 0
    error_message = "existing_network_id обязателен"
  }
}

variable "existing_subnet_id" {
  type = string
  validation {
    condition     = length(var.existing_subnet_id) > 0
    error_message = "existing_subnet_id обязателен"
  }
}

variable "sa_id" {
  description = "ID существующего SA из hw6/7. Если пусто — создадим новый."
  type        = string
  default     = ""
}

variable "sa_name" {
  type    = string
  default = "mlops-hw8-sa"
}

variable "kafka_cluster_name" {
  type    = string
  default = "mlops-hw8-kafka"
}

variable "kafka_user_password" {
  description = "Пароль пользователя Kafka. Если пусто — генерируем."
  type        = string
  default     = ""
  sensitive   = true
}

variable "create_airflow" {
  description = "Создавать ли Managed Airflow (true если в hw7 удалён)"
  type        = bool
  default     = false
}

variable "airflow_admin_password" {
  type      = string
  default   = ""
  sensitive = true
}

variable "ssh_pubkey" {
  description = "SSH-ключ для Data Proc"
  type        = string
  default     = ""
}

variable "bucket_name" {
  description = "Если используешь существующий бакет hw6 — впиши его. Если пусто — создадим mlops-hw8-..."
  type        = string
  default     = ""
}
