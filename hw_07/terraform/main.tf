################################################################################
# 1. SERVICE ACCOUNT + ROLES
################################################################################

resource "yandex_iam_service_account" "sa" {
  name        = var.sa_name
  description = "Airflow + Data Proc + MLflow VM SA (MLOps HW7)"
  folder_id   = var.yc_folder_id
}

locals {
  sa_roles = [
    "managed-airflow.integrationProvider",
    "storage.editor",
    "dataproc.agent",
    "dataproc.provisioner",
    "dataproc.editor",
    "vpc.user",
    "monitoring.editor",
    "iam.serviceAccounts.user",
    "compute.editor",  # для VM
  ]
}

resource "yandex_resourcemanager_folder_iam_member" "sa_roles" {
  for_each  = toset(local.sa_roles)
  folder_id = var.yc_folder_id
  role      = each.value
  member    = "serviceAccount:${yandex_iam_service_account.sa.id}"
}

resource "yandex_iam_service_account_static_access_key" "sa_static_key" {
  service_account_id = yandex_iam_service_account.sa.id
  description        = "Static key for S3"
}

resource "time_sleep" "wait_iam_propagation" {
  depends_on      = [yandex_resourcemanager_folder_iam_member.sa_roles]
  create_duration = "30s"
}

################################################################################
# 2. BUCKET
################################################################################

resource "yandex_storage_bucket" "main" {
  bucket     = var.bucket_name
  access_key = yandex_iam_service_account_static_access_key.sa_static_key.access_key
  secret_key = yandex_iam_service_account_static_access_key.sa_static_key.secret_key
  acl        = "private"

  depends_on = [time_sleep.wait_iam_propagation]
}

resource "yandex_storage_object" "placeholder_dags" {
  bucket     = yandex_storage_bucket.main.bucket
  key        = "dags/.placeholder"
  content    = "dags"
  access_key = yandex_iam_service_account_static_access_key.sa_static_key.access_key
  secret_key = yandex_iam_service_account_static_access_key.sa_static_key.secret_key
}

resource "yandex_storage_object" "placeholder_scripts" {
  bucket     = yandex_storage_bucket.main.bucket
  key        = "scripts/.placeholder"
  content    = "scripts"
  access_key = yandex_iam_service_account_static_access_key.sa_static_key.access_key
  secret_key = yandex_iam_service_account_static_access_key.sa_static_key.secret_key
}

resource "yandex_storage_object" "placeholder_mlflow" {
  bucket     = yandex_storage_bucket.main.bucket
  key        = "mlflow/.placeholder"
  content    = "mlflow artifact root"
  access_key = yandex_iam_service_account_static_access_key.sa_static_key.access_key
  secret_key = yandex_iam_service_account_static_access_key.sa_static_key.secret_key
}

################################################################################
# 3. SECURITY GROUP — для Airflow + MLflow VM + Data Proc
################################################################################

resource "yandex_vpc_security_group" "main_sg" {
  name       = "mlops-hw7-sg"
  network_id = var.existing_network_id

  ingress {
    description       = "Self traffic"
    protocol          = "ANY"
    from_port         = 0
    to_port           = 65535
    predefined_target = "self_security_group"
  }
  egress {
    description       = "Self traffic"
    protocol          = "ANY"
    from_port         = 0
    to_port           = 65535
    predefined_target = "self_security_group"
  }

  ingress {
    description    = "SSH к MLflow VM"
    protocol       = "TCP"
    port           = 22
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description    = "MLflow Web UI / API"
    protocol       = "TCP"
    port           = 5000
    v4_cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description    = "All outbound"
    protocol       = "ANY"
    from_port      = 0
    to_port        = 65535
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
}

################################################################################
# 4. ПАРОЛИ
################################################################################

resource "random_password" "airflow_admin" {
  length      = 16
  special     = true
  min_special = 2
  # Yandex Managed Airflow запрещает '$' и '`'
  override_special = "!#%*+-=?@_"
}

resource "random_password" "pg_password" {
  length  = 24
  special = false   # без спецсимволов — иначе мешает PostgreSQL/cloud-init
}

locals {
  airflow_admin_password = (
    var.airflow_admin_password != ""
    ? var.airflow_admin_password
    : random_password.airflow_admin.result
  )
}

################################################################################
# 5. MLFLOW VM (compute instance)
################################################################################

# Образ Ubuntu 22.04 LTS
data "yandex_compute_image" "ubuntu" {
  family = "ubuntu-2204-lts"
}

resource "yandex_compute_instance" "mlflow_vm" {
  name        = var.mlflow_vm_name
  description = "MLflow Tracking Server (with embedded PostgreSQL)"
  zone        = var.yc_zone
  hostname    = "mlflow"

  service_account_id = yandex_iam_service_account.sa.id

  resources {
    cores  = 2
    memory = 4
  }

  boot_disk {
    initialize_params {
      image_id = data.yandex_compute_image.ubuntu.id
      size     = 20
      type     = "network-hdd"
    }
  }

  network_interface {
    subnet_id          = var.existing_subnet_id
    nat                = true   # публичный IP — для доступа к MLflow UI
    security_group_ids = [yandex_vpc_security_group.main_sg.id]
  }

  metadata = {
    serial-port-enable = "1"
    user-data          = templatefile("${path.module}/cloud-init/mlflow.yaml.tpl", {
      ssh_pubkey     = var.ssh_pubkey
      pg_password    = random_password.pg_password.result
      bucket         = yandex_storage_bucket.main.bucket
      aws_access_key = yandex_iam_service_account_static_access_key.sa_static_key.access_key
      aws_secret_key = yandex_iam_service_account_static_access_key.sa_static_key.secret_key
    })
  }

  depends_on = [
    yandex_storage_bucket.main,
    yandex_resourcemanager_folder_iam_member.sa_roles,
    time_sleep.wait_iam_propagation,
  ]
}

################################################################################
# 6. MANAGED AIRFLOW
################################################################################

resource "yandex_airflow_cluster" "this" {
  name        = var.airflow_cluster_name
  description = "MLOps HW7 — Managed Airflow"

  service_account_id = yandex_iam_service_account.sa.id
  subnet_ids         = [var.existing_subnet_id]
  security_group_ids = [yandex_vpc_security_group.main_sg.id]

  admin_password = local.airflow_admin_password

  code_sync = {
    s3 = {
      bucket = yandex_storage_bucket.main.bucket
    }
  }

  webserver = {
    count              = 1
    resource_preset_id = "c1-m4"
  }
  scheduler = {
    count              = 1
    resource_preset_id = "c1-m4"
  }
  worker = {
    min_count          = 1
    max_count          = 1
    resource_preset_id = "c1-m4"
  }
  triggerer = {
    count              = 1
    resource_preset_id = "c1-m4"
  }

  pip_packages = [
    "apache-airflow-providers-yandex",
    "mlflow==2.16.2",
  ]

  logging = {
    enabled   = true
    folder_id = var.yc_folder_id
    min_level = "INFO"
  }

  depends_on = [
    yandex_resourcemanager_folder_iam_member.sa_roles,
    time_sleep.wait_iam_propagation,
    yandex_storage_object.placeholder_dags,
  ]
}
