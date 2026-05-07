################################################################################
# 1. SERVICE ACCOUNT (новый, если нет существующего)
################################################################################

locals {
  use_existing_sa = var.sa_id != ""
}

resource "yandex_iam_service_account" "sa" {
  count       = local.use_existing_sa ? 0 : 1
  name        = var.sa_name
  description = "MLOps HW8 SA (Kafka + Data Proc + MLflow)"
  folder_id   = var.yc_folder_id
}

locals {
  sa_id_effective = local.use_existing_sa ? var.sa_id : yandex_iam_service_account.sa[0].id

  sa_roles = [
    "managed-airflow.integrationProvider",
    "storage.editor",
    "dataproc.agent",
    "dataproc.provisioner",
    "dataproc.editor",
    "vpc.user",
    "monitoring.editor",
    "iam.serviceAccounts.user",
    "compute.editor",
    "managed-kafka.editor",
    "kms.editor",
  ]
}

resource "yandex_resourcemanager_folder_iam_member" "sa_roles" {
  for_each  = toset(local.sa_roles)
  folder_id = var.yc_folder_id
  role      = each.value
  member    = "serviceAccount:${local.sa_id_effective}"
}

resource "yandex_iam_service_account_static_access_key" "sa_static_key" {
  count              = local.use_existing_sa ? 0 : 1
  service_account_id = local.sa_id_effective
  description        = "Static key for S3"
}

resource "time_sleep" "wait_iam" {
  depends_on      = [yandex_resourcemanager_folder_iam_member.sa_roles]
  create_duration = "30s"
}

################################################################################
# 2. BUCKET (создаётся только если bucket_name пуст)
################################################################################

resource "yandex_storage_bucket" "main" {
  count      = var.bucket_name == "" ? 1 : 0
  bucket     = "mlops-hw8-${random_password.bucket_suffix.result}"
  access_key = local.use_existing_sa ? null : yandex_iam_service_account_static_access_key.sa_static_key[0].access_key
  secret_key = local.use_existing_sa ? null : yandex_iam_service_account_static_access_key.sa_static_key[0].secret_key
  acl        = "private"
  depends_on = [time_sleep.wait_iam]
}

resource "random_password" "bucket_suffix" {
  length  = 8
  special = false
  upper   = false
}

locals {
  bucket_name_effective = var.bucket_name != "" ? var.bucket_name : yandex_storage_bucket.main[0].bucket
}

################################################################################
# 3. SECURITY GROUP — общая для Kafka + Airflow + Data Proc
################################################################################

resource "yandex_vpc_security_group" "main_sg" {
  name       = "mlops-hw8-sg"
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
    description    = "Kafka SSL"
    protocol       = "TCP"
    port           = 9091
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description    = "Kafka plaintext (только для dev)"
    protocol       = "TCP"
    port           = 9092
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description    = "SSH"
    protocol       = "TCP"
    port           = 22
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
# 4. KAFKA cluster + topics + user
################################################################################

resource "random_password" "kafka_pass" {
  length  = 24
  special = false
}

locals {
  kafka_pass_effective = (
    var.kafka_user_password != ""
    ? var.kafka_user_password
    : random_password.kafka_pass.result
  )
}

resource "yandex_mdb_kafka_cluster" "this" {
  name        = var.kafka_cluster_name
  environment = "PRESTABLE"
  network_id  = var.existing_network_id
  subnet_ids  = [var.existing_subnet_id]

  security_group_ids = [yandex_vpc_security_group.main_sg.id]

  config {
    version          = "3.9"
    brokers_count    = 1
    zones            = [var.yc_zone]
    assign_public_ip = true
    schema_registry  = false

    kafka {
      resources {
        resource_preset_id = "s2.micro"
        disk_size          = 32
        disk_type_id       = "network-ssd"
      }
    }
  }
}

resource "yandex_mdb_kafka_topic" "transactions" {
  cluster_id         = yandex_mdb_kafka_cluster.this.id
  name               = "transactions"
  partitions         = 3
  replication_factor = 1
}

resource "yandex_mdb_kafka_topic" "predictions" {
  cluster_id         = yandex_mdb_kafka_cluster.this.id
  name               = "predictions"
  partitions         = 3
  replication_factor = 1
}

resource "yandex_mdb_kafka_user" "user" {
  cluster_id = yandex_mdb_kafka_cluster.this.id
  name       = "mlops-user"
  password   = local.kafka_pass_effective

  permission {
    topic_name = "transactions"
    role       = "ACCESS_ROLE_PRODUCER"
  }
  permission {
    topic_name = "transactions"
    role       = "ACCESS_ROLE_CONSUMER"
  }
  permission {
    topic_name = "predictions"
    role       = "ACCESS_ROLE_PRODUCER"
  }
  permission {
    topic_name = "predictions"
    role       = "ACCESS_ROLE_CONSUMER"
  }
}

################################################################################
# 5. AIRFLOW (только если create_airflow = true)
################################################################################

resource "random_password" "airflow_admin" {
  length           = 16
  special          = true
  min_special      = 2
  override_special = "!#%*+-=?@_"
}

locals {
  airflow_admin_pass_effective = (
    var.airflow_admin_password != ""
    ? var.airflow_admin_password
    : random_password.airflow_admin.result
  )
}

resource "yandex_airflow_cluster" "this" {
  count       = var.create_airflow ? 1 : 0
  name        = "mlops-hw8-airflow"
  description = "MLOps HW8 Managed Airflow"

  service_account_id = local.sa_id_effective
  subnet_ids         = [var.existing_subnet_id]
  security_group_ids = [yandex_vpc_security_group.main_sg.id]

  admin_password = local.airflow_admin_pass_effective

  code_sync = {
    s3 = { bucket = local.bucket_name_effective }
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

  depends_on = [
    yandex_resourcemanager_folder_iam_member.sa_roles,
    time_sleep.wait_iam,
  ]
}
