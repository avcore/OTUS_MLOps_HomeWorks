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

variable "ssh_pubkey" {
  type    = string
  default = ""
}

variable "k8s_cluster_name" {
  type    = string
  default = "mlops-hw9-k8s"
}

variable "registry_name" {
  type    = string
  default = "mlops-hw9-cr"
}

variable "k8s_node_count" {
  description = "Сколько нод в node-group (3 — обязательное требование hw9)"
  type        = number
  default     = 3
}
