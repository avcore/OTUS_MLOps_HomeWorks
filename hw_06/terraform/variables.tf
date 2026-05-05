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

variable "bucket_name" {
  description = "Globally unique bucket для DAGs/scripts/MLflow artifacts/raw"
  type        = string
}

variable "existing_network_id" {
  type = string
  validation {
    condition     = length(var.existing_network_id) > 0
    error_message = "existing_network_id обязателен. См. `yc vpc network list`"
  }
}

variable "existing_subnet_id" {
  type = string
  validation {
    condition     = length(var.existing_subnet_id) > 0
    error_message = "existing_subnet_id обязателен. См. `yc vpc subnet list`"
  }
}

variable "ssh_pubkey" {
  description = "Содержимое ~/.ssh/id_rsa.pub — для SSH в MLflow VM"
  type        = string

  validation {
    condition     = length(var.ssh_pubkey) > 50
    error_message = "Задайте ssh_pubkey в terraform.tfvars"
  }
}

variable "airflow_admin_password" {
  type      = string
  sensitive = true
  default   = ""
}

variable "sa_name" {
  type    = string
  default = "mlops-hw6-sa"
}

variable "airflow_cluster_name" {
  type    = string
  default = "mlops-hw6-airflow"
}

variable "mlflow_vm_name" {
  type    = string
  default = "mlops-hw6-mlflow"
}
