################################################################################
# 1. SERVICE ACCOUNTS
#    - sa_cluster: для control plane k8s (создавать сетевые ресурсы)
#    - sa_node:    для нод (тянуть образы из CR, ходить в VPC)
################################################################################

resource "yandex_iam_service_account" "sa_cluster" {
  name      = "mlops-hw9-k8s-cluster-sa"
  folder_id = var.yc_folder_id
}

resource "yandex_iam_service_account" "sa_node" {
  name      = "mlops-hw9-k8s-node-sa"
  folder_id = var.yc_folder_id
}

locals {
  cluster_roles = ["k8s.clusters.agent", "vpc.publicAdmin", "load-balancer.admin"]
  node_roles    = ["container-registry.images.puller"]
}

resource "yandex_resourcemanager_folder_iam_member" "cluster_sa_roles" {
  for_each  = toset(local.cluster_roles)
  folder_id = var.yc_folder_id
  role      = each.value
  member    = "serviceAccount:${yandex_iam_service_account.sa_cluster.id}"
}

resource "yandex_resourcemanager_folder_iam_member" "node_sa_roles" {
  for_each  = toset(local.node_roles)
  folder_id = var.yc_folder_id
  role      = each.value
  member    = "serviceAccount:${yandex_iam_service_account.sa_node.id}"
}

resource "time_sleep" "wait_iam" {
  depends_on = [
    yandex_resourcemanager_folder_iam_member.cluster_sa_roles,
    yandex_resourcemanager_folder_iam_member.node_sa_roles,
  ]
  create_duration = "30s"
}

################################################################################
# 2. CONTAINER REGISTRY (для Docker образов)
################################################################################

resource "yandex_container_registry" "this" {
  name      = var.registry_name
  folder_id = var.yc_folder_id
}

################################################################################
# 3. SECURITY GROUP — k8s + service load balancer
################################################################################

resource "yandex_vpc_security_group" "k8s_sg" {
  name       = "mlops-hw9-k8s-sg"
  network_id = var.existing_network_id

  # Internal — между нодами и control plane
  ingress {
    description       = "Self"
    protocol          = "ANY"
    from_port         = 0
    to_port           = 65535
    predefined_target = "self_security_group"
  }
  egress {
    description       = "Self"
    protocol          = "ANY"
    from_port         = 0
    to_port           = 65535
    predefined_target = "self_security_group"
  }

  # k8s API health checks
  ingress {
    description       = "Health checks"
    protocol          = "TCP"
    predefined_target = "loadbalancer_healthchecks"
    from_port         = 0
    to_port           = 65535
  }

  # Сервисы LoadBalancer (наш FastAPI публикуется на 80)
  ingress {
    description    = "Service load balancer (HTTP)"
    protocol       = "TCP"
    port           = 80
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description    = "NodePort range (на всякий)"
    protocol       = "TCP"
    from_port      = 30000
    to_port        = 32767
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
# 4. KUBERNETES CLUSTER + NODE GROUP
################################################################################

resource "yandex_kubernetes_cluster" "this" {
  name       = var.k8s_cluster_name
  network_id = var.existing_network_id

  service_account_id      = yandex_iam_service_account.sa_cluster.id
  node_service_account_id = yandex_iam_service_account.sa_node.id

  master {
    version   = "1.32"
    public_ip = true

    zonal {
      zone      = var.yc_zone
      subnet_id = var.existing_subnet_id
    }

    security_group_ids = [yandex_vpc_security_group.k8s_sg.id]
  }

  release_channel = "REGULAR"

  depends_on = [time_sleep.wait_iam]
}

resource "yandex_kubernetes_node_group" "workers" {
  cluster_id = yandex_kubernetes_cluster.this.id
  name       = "mlops-hw9-workers"
  version    = "1.32"

  scale_policy {
    fixed_scale {
      size = var.k8s_node_count
    }
  }

  allocation_policy {
    location {
      zone = var.yc_zone
    }
  }

  instance_template {
    platform_id = "standard-v3"
    resources {
      memory = 4
      cores  = 2
    }
    boot_disk {
      type = "network-hdd"
      size = 64
    }
    network_interface {
      subnet_ids         = [var.existing_subnet_id]
      nat                = true
      security_group_ids = [yandex_vpc_security_group.k8s_sg.id]
    }
    metadata = var.ssh_pubkey != "" ? {
      ssh-keys = "ubuntu:${var.ssh_pubkey}"
    } : {}
    container_runtime {
      type = "containerd"
    }
  }

  maintenance_policy {
    auto_upgrade = true
    auto_repair  = true
  }
}
