output "registry_id" {
  description = "ID Container Registry — нужен для тэга образа cr.yandex/<id>/..."
  value       = yandex_container_registry.this.id
}

output "registry_url_prefix" {
  value = "cr.yandex/${yandex_container_registry.this.id}"
}

output "k8s_cluster_id" {
  value = yandex_kubernetes_cluster.this.id
}

output "k8s_cluster_name" {
  value = yandex_kubernetes_cluster.this.name
}

output "kubeconfig_command" {
  description = "Команда для получения kubeconfig локально"
  value       = "yc managed-kubernetes cluster get-credentials --id ${yandex_kubernetes_cluster.this.id} --external --force"
}

output "cluster_sa_id" {
  value = yandex_iam_service_account.sa_cluster.id
}

output "node_sa_id" {
  value = yandex_iam_service_account.sa_node.id
}

output "github_secrets_to_set" {
  description = "Что положить в GitHub Settings → Secrets"
  value = {
    YC_REGISTRY_ID  = yandex_container_registry.this.id
    YC_K8S_CLUSTER_ID = yandex_kubernetes_cluster.this.id
    # YC_SA_JSON_CREDENTIALS — отдельно, см. README шаг 4
  }
}
