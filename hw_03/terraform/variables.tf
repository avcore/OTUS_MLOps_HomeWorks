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
  description = "Default zone"
  type        = string
  default     = "ru-central1-a"
}

variable "bucket_name" {
  description = "Globally unique bucket name"
  type        = string
}

variable "ssh_pubkey" {
  description = "Public SSH key contents (one line, ssh-rsa ...)"
  type        = string
}

variable "cluster_name" {
  description = "Data Proc cluster name"
  type        = string
  default     = "mlops-hw3-spark"
}

variable "sa_name" {
  description = "Service account name"
  type        = string
  default     = "mlops-hw3-sa"
}

# Если оставить пустыми — будет использоваться существующая сеть/подсеть в каталоге
# (рекомендуется, чтобы не упереться в квоту vpc.networks.count).
# Если задать — создавать сеть НЕ нужно, но конфиг ожидает что сеть/подсеть уже существуют.
variable "existing_network_id" {
  description = "ID существующей VPC-сети. Получить: `yc vpc network list`"
  type        = string

  validation {
    condition     = length(var.existing_network_id) > 0
    error_message = "Задайте existing_network_id в terraform.tfvars. Список сетей: `yc vpc network list`"
  }
}

variable "existing_subnet_id" {
  description = "ID существующей VPC-подсети в зоне yc_zone. Получить: `yc vpc subnet list`"
  type        = string

  validation {
    condition     = length(var.existing_subnet_id) > 0
    error_message = "Задайте existing_subnet_id в terraform.tfvars. Список подсетей: `yc vpc subnet list`"
  }
}
