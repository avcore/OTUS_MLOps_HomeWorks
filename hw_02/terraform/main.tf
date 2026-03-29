############################################
# Existing network / subnet
############################################
data "yandex_vpc_network" "existing" {
  network_id = var.existing_network_id
}

resource "yandex_vpc_gateway" "nat_gateway" {
  name = "otus-mlops-${var.environment}-nat-gateway"

  shared_egress_gateway {}
}

resource "yandex_vpc_route_table" "dataproc_rt" {
  name       = "otus-mlops-${var.environment}-route-table"
  network_id = data.yandex_vpc_network.existing.id

  static_route {
    destination_prefix = "0.0.0.0/0"
    gateway_id         = yandex_vpc_gateway.nat_gateway.id
  }
}

resource "yandex_vpc_subnet" "dataproc_subnet" {
  name           = "otus-mlops-${var.environment}-subnet"
  zone           = var.zone
  network_id     = data.yandex_vpc_network.existing.id
  v4_cidr_blocks = [var.network_cidr]
  route_table_id = yandex_vpc_route_table.dataproc_rt.id
}

############################################
# Security group for Data Proc
############################################
resource "yandex_vpc_security_group" "dataproc_sg" {
  name       = "otus-mlops-${var.environment}-dataproc-sg"
  network_id = data.yandex_vpc_network.existing.id

  ingress {
    protocol       = "TCP"
    description    = "SSH"
    v4_cidr_blocks = [var.ssh_allowed_cidr]
    port           = 22
  }

  ingress {
    protocol          = "ANY"
    description       = "Intra-cluster"
    predefined_target = "self_security_group"
  }

  egress {
    protocol       = "ANY"
    description    = "All outbound"
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
}

############################################
# Service account
############################################
resource "yandex_iam_service_account" "sa" {
  name        = "otus-mlops-${var.environment}-sa"
  description = "Service account for OTUS MLOps HW02 (Object Storage + Data Proc)"
}

resource "yandex_resourcemanager_folder_iam_member" "dp_agent" {
  folder_id = var.folder_id
  role      = "mdb.dataproc.agent"
  member    = "serviceAccount:${yandex_iam_service_account.sa.id}"
}

resource "yandex_resourcemanager_folder_iam_member" "storage_admin" {
  folder_id = var.folder_id
  role      = "storage.admin"
  member    = "serviceAccount:${yandex_iam_service_account.sa.id}"
}

resource "yandex_resourcemanager_folder_iam_member" "vpc_user" {
  folder_id = var.folder_id
  role      = "vpc.user"
  member    = "serviceAccount:${yandex_iam_service_account.sa.id}"
}

############################################
# Storage access key
############################################
resource "yandex_iam_service_account_static_access_key" "sa_key" {
  service_account_id = yandex_iam_service_account.sa.id
  description        = "Static access key for s3cmd/CLI (HW02)."
}

############################################
# Bucket
############################################
resource "yandex_storage_bucket" "target" {
  bucket = var.bucket_name

  access_key = yandex_iam_service_account_static_access_key.sa_key.access_key
  secret_key = yandex_iam_service_account_static_access_key.sa_key.secret_key

  anonymous_access_flags {
    read        = var.public_bucket_read
    list        = var.public_bucket_read
    config_read = var.public_bucket_read
  }

  default_storage_class = "STANDARD"
}

############################################
# Data Proc cluster
############################################
resource "yandex_dataproc_cluster" "this" {
  bucket             = yandex_storage_bucket.target.bucket
  name               = var.dataproc_cluster_name
  description        = "OTUS MLOps HW2 Data Proc cluster"
  service_account_id = yandex_iam_service_account.sa.id
  zone_id            = var.zone
  ui_proxy           = var.enable_ui_proxy

  cluster_config {
    version_id = var.dataproc_version

    hadoop {
      services        = ["HDFS", "YARN", "SPARK", "MAPREDUCE", "HIVE"]
      ssh_public_keys = [file(var.public_key_path)]
    }

    subcluster_spec {
      name             = "master"
      role             = "MASTERNODE"
      subnet_id        = yandex_vpc_subnet.dataproc_subnet.id
      hosts_count      = 1
      assign_public_ip = true

      resources {
        resource_preset_id = "s3-c2-m8"
        disk_type_id       = "network-hdd"
        disk_size          = 40
      }
    }

    subcluster_spec {
      name             = "data"
      role             = "DATANODE"
      subnet_id        = yandex_vpc_subnet.dataproc_subnet.id
      hosts_count      = 3
      assign_public_ip = false

      resources {
        resource_preset_id = "s3-c4-m16"
        disk_type_id       = "network-hdd"
        disk_size          = 128
      }
    }
  }

  security_group_ids = [yandex_vpc_security_group.dataproc_sg.id]

  depends_on = [
    yandex_resourcemanager_folder_iam_member.dp_agent,
    yandex_resourcemanager_folder_iam_member.storage_admin,
    yandex_resourcemanager_folder_iam_member.vpc_user
  ]
}
