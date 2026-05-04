################################################################################
# 1. СЕРВИСНЫЙ АККАУНТ + РОЛИ
#    Один SA для:
#    - самого Airflow кластера (читать DAG'и из S3, писать логи)
#    - кластеров Data Proc, которые DAG будет создавать (тот же SA)
################################################################################

resource "yandex_iam_service_account" "sa" {
  name        = var.sa_name
  description = "Airflow + Data Proc service account (MLOps HW5)"
  folder_id   = var.yc_folder_id
}

locals {
  sa_roles = [
    # для Managed Airflow
    "managed-airflow.integrationProvider",
    "storage.editor",            # читать/писать DAG'и в S3, писать логи
    # для Data Proc, который Airflow создаёт
    "dataproc.agent",
    "dataproc.provisioner",
    "dataproc.editor",           # для CRUD кластера через API
    "vpc.user",
    "monitoring.editor",
    # чтобы Airflow мог "от имени" этого SA создавать Data Proc
    "iam.serviceAccounts.user",
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
  description        = "Static key for S3 access"
}

resource "time_sleep" "wait_iam_propagation" {
  depends_on      = [yandex_resourcemanager_folder_iam_member.sa_roles]
  create_duration = "30s"
}

################################################################################
# 2. BUCKET для DAGs + скриптов + (опц.) логов Airflow
################################################################################

resource "yandex_storage_bucket" "airflow_bucket" {
  bucket     = var.bucket_name
  access_key = yandex_iam_service_account_static_access_key.sa_static_key.access_key
  secret_key = yandex_iam_service_account_static_access_key.sa_static_key.secret_key

  acl = "private"   # для Airflow приватный, в отличие от hw3

  depends_on = [
    yandex_resourcemanager_folder_iam_member.sa_roles,
    time_sleep.wait_iam_propagation,
  ]
}

# Заранее создаём "папку" dags/ — Airflow ожидает её увидеть
resource "yandex_storage_object" "dags_placeholder" {
  bucket     = yandex_storage_bucket.airflow_bucket.bucket
  key        = "dags/.placeholder"
  content    = "placeholder for dags folder"
  access_key = yandex_iam_service_account_static_access_key.sa_static_key.access_key
  secret_key = yandex_iam_service_account_static_access_key.sa_static_key.secret_key
}

resource "yandex_storage_object" "scripts_placeholder" {
  bucket     = yandex_storage_bucket.airflow_bucket.bucket
  key        = "scripts/.placeholder"
  content    = "placeholder for spark scripts"
  access_key = yandex_iam_service_account_static_access_key.sa_static_key.access_key
  secret_key = yandex_iam_service_account_static_access_key.sa_static_key.secret_key
}

################################################################################
# 3. SECURITY GROUP для Airflow (использует ту же сеть, что и Data Proc)
################################################################################

resource "yandex_vpc_security_group" "airflow_sg" {
  name       = "mlops-hw5-airflow-sg"
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

  egress {
    description    = "Outbound HTTPS (Object Storage, API)"
    protocol       = "TCP"
    port           = 443
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
# 4. ПАРОЛЬ ДЛЯ AIRFLOW UI (если не задан — генерируем)
################################################################################

resource "random_password" "airflow_admin" {
  length      = 16
  special     = true
  min_special = 2
  override_special = "!#$%*+-=?@_"
}

locals {
  airflow_admin_password = (
    var.airflow_admin_password != ""
    ? var.airflow_admin_password
    : random_password.airflow_admin.result
  )
}

################################################################################
# 5. УПРАВЛЯЕМЫЙ AIRFLOW
################################################################################

resource "yandex_airflow_cluster" "this" {
  name        = var.airflow_cluster_name
  description = "MLOps HW5 — Managed Airflow"

  service_account_id = yandex_iam_service_account.sa.id
  subnet_ids         = [var.existing_subnet_id]
  security_group_ids = [yandex_vpc_security_group.airflow_sg.id]

  admin_password = local.airflow_admin_password

  # ВАЖНО: в провайдере yandex >= 0.200 эти блоки задаются через "=" как
  # аргументы-объекты, а НЕ как вложенные nested blocks.
  code_sync = {
    s3 = {
      bucket = yandex_storage_bucket.airflow_bucket.bucket
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
  ]

  logging = {
    enabled   = true
    folder_id = var.yc_folder_id
    min_level = "INFO"
  }

  # airflow_config = {
  #   "core.load_examples" = "False"
  # }

  depends_on = [
    yandex_resourcemanager_folder_iam_member.sa_roles,
    time_sleep.wait_iam_propagation,
    yandex_storage_object.dags_placeholder,
  ]
}