################################################################################
# 1. СЕРВИСНЫЙ АККАУНТ + РОЛИ
################################################################################

resource "yandex_iam_service_account" "sa" {
  name        = var.sa_name
  description = "Service account for Yandex Data Processing cluster (MLOps HW3)"
  folder_id   = var.yc_folder_id
}

# Роли согласно официальной документации Yandex Data Processing:
# https://yandex.cloud/ru/docs/data-proc/operations/cluster-create
# storage.admin вместо storage.editor — потому что editor НЕ даёт права
# создавать/удалять бакеты, только работать с объектами в них.
locals {
  sa_roles = [
    "dataproc.agent",
    "dataproc.provisioner",
    "storage.admin",
    "vpc.user",
    "monitoring.viewer",
  ]
}

resource "yandex_resourcemanager_folder_iam_member" "sa_roles" {
  for_each  = toset(local.sa_roles)
  folder_id = var.yc_folder_id
  role      = each.value
  member    = "serviceAccount:${yandex_iam_service_account.sa.id}"
}

# Статический ключ для доступа SA к S3-совместимому Object Storage
resource "yandex_iam_service_account_static_access_key" "sa_static_key" {
  service_account_id = yandex_iam_service_account.sa.id
  description        = "Static key for S3 access"
}

# Ждём пропагацию IAM-ролей (S3 API использует кэш ~10 секунд)
resource "time_sleep" "wait_iam_propagation" {
  depends_on      = [yandex_resourcemanager_folder_iam_member.sa_roles]
  create_duration = "30s"
}

################################################################################
# 2. BUCKET
################################################################################

resource "yandex_storage_bucket" "data_bucket" {
  bucket     = var.bucket_name
  access_key = yandex_iam_service_account_static_access_key.sa_static_key.access_key
  secret_key = yandex_iam_service_account_static_access_key.sa_static_key.secret_key

  # Публичное чтение для проверки преподавателем (требование задания)
  acl = "public-read"

  anonymous_access_flags {
    read = true
    list = true
  }

  depends_on = [
    yandex_resourcemanager_folder_iam_member.sa_roles,
    time_sleep.wait_iam_propagation,
  ]
}

################################################################################
# 3. СЕТЬ — переиспользуем существующую (чтобы обойти квоту vpc.networks.count)
################################################################################

# Источники: либо явно заданный ID, либо берём первую попавшуюся сеть/подсеть
# в каталоге. Yandex CLI заранее уже создал default-сеть и default-подсеть.

data "yandex_vpc_network" "existing" {
  count      = var.existing_network_id == "" ? 0 : 1
  network_id = var.existing_network_id
}

data "yandex_vpc_subnet" "existing" {
  count     = var.existing_subnet_id == "" ? 0 : 1
  subnet_id = var.existing_subnet_id
}

locals {
  network_id = var.existing_network_id
  subnet_id  = var.existing_subnet_id
}

resource "yandex_vpc_security_group" "dataproc_sg" {
  name       = "mlops-hw3-dataproc-sg"
  network_id = local.network_id

  # Внутрикластерный трафик (как требует Data Proc документация)
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

  # Доступ к Object Storage и метаданным
  egress {
    description    = "Outbound HTTPS"
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

  # SSH к мастеру
  ingress {
    description    = "SSH"
    protocol       = "TCP"
    port           = 22
    v4_cidr_blocks = ["0.0.0.0/0"]
  }

  # Jupyter UI
  ingress {
    description    = "Jupyter Notebook"
    protocol       = "TCP"
    port           = 8888
    v4_cidr_blocks = ["0.0.0.0/0"]
  }

  # Spark UI
  ingress {
    description    = "Spark UI"
    protocol       = "TCP"
    from_port      = 4040
    to_port        = 4050
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
}

################################################################################
# 4. SPARK-КЛАСТЕР YANDEX DATA PROCESSING
################################################################################

resource "yandex_dataproc_cluster" "spark" {
  name               = var.cluster_name
  description        = "MLOps HW3 — Spark cluster"
  service_account_id = yandex_iam_service_account.sa.id
  zone_id            = var.yc_zone
  bucket             = yandex_storage_bucket.data_bucket.bucket
  security_group_ids = [yandex_vpc_security_group.dataproc_sg.id]

  ui_proxy = true

  cluster_config {
    version_id = "2.1"

    hadoop {
      services = ["HDFS", "YARN", "SPARK", "TEZ", "MAPREDUCE"]

      ssh_public_keys = [var.ssh_pubkey]

      properties = {
        "yarn:yarn.resourcemanager.am.max-attempts" = "5"
      }
    }

    subcluster_spec {
      name = "master"
      role = "MASTERNODE"
      resources {
        resource_preset_id = "s3-c2-m8"
        disk_type_id       = "network-hdd"
        disk_size          = 40
      }
      subnet_id        = local.subnet_id
      hosts_count      = 1
      assign_public_ip = true
    }

    subcluster_spec {
      name = "data"
      role = "DATANODE"
      resources {
        resource_preset_id = "s3-c4-m16"
        disk_type_id       = "network-hdd"
        disk_size          = 128
      }
      subnet_id        = local.subnet_id
      hosts_count      = 3
      assign_public_ip = false
    }
  }

  depends_on = [
    yandex_resourcemanager_folder_iam_member.sa_roles,
    yandex_storage_bucket.data_bucket,
  ]
}
