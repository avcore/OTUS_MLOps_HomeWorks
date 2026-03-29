variable "yc_token" {
  description = "Yandex Cloud IAM token (or set YC_TOKEN env var and pass via -var)."
  type        = string
  sensitive   = true
}

variable "cloud_id" {
  description = "Cloud ID"
  type        = string
}

variable "folder_id" {
  description = "Folder ID"
  type        = string
}

variable "zone" {
  description = "Default zone for resources, e.g. ru-central1-a"
  type        = string
  default     = "ru-central1-a"
}

variable "network_cidr" {
  description = "CIDR block for the Data Proc subnet"
  type        = string
  default     = "10.200.0.0/24"
}

variable "bucket_name" {
  description = "Your target Object Storage bucket name (must be globally unique)"
  type        = string
}

variable "dataproc_cluster_name" {
  description = "YDP (Data Proc) cluster name"
  type        = string
  default     = "otus-mlops-dp"
}

variable "dataproc_version_id" {
  description = "Data Proc version ID. Keep default unless your course requires specific version."
  type        = string
  default     = "2.0"
}

variable "public_bucket_read" {
  description = "If true, enables anonymous read+list for the bucket (required for homework review)."
  type        = bool
  default     = true
}


variable "ssh_allowed_cidr" {
  description = "CIDR allowed to SSH to Data Proc master. Restrict to your external IP, e.g. 203.0.113.10/32."
  type        = string
  default     = "0.0.0.0/0"
}

variable "enable_ui_proxy" {
  description = "Enable Yandex Data Proc UI proxy. Keep true for convenience, false to reduce exposed surface."
  type        = bool
  default     = true
}

variable "environment" {
  description = "Environment label for tagging and naming."
  type        = string
  default     = "hw02"
}

variable "price_vcpu_hourly" {
  description = "Estimated hourly price per vCPU for Yandex Data Proc cost model."
  type        = number
  default     = 0.011790
}

variable "price_ram_gb_hourly" {
  description = "Estimated hourly price per GB RAM for Yandex Data Proc cost model."
  type        = number
  default     = 0.003060
}

variable "price_network_hdd_gb_hourly" {
  description = "Estimated hourly price per GB of network-hdd for cost model."
  type        = number
  default     = 0.000042
}

variable "price_object_storage_standard_gb_monthly" {
  description = "Estimated monthly price per GB of Object Storage STANDARD for comparison against HDFS."
  type        = number
  default     = 0.018090
}

variable "dataproc_version" {
  description = "Yandex Data Processing image version"
  type        = string
  default     = "2.0"
}

variable "existing_network_id" {
  description = "Existing VPC network ID"
  type        = string
}

variable "public_key_path" {
  description = "Path to SSH public key"
  type        = string
}
