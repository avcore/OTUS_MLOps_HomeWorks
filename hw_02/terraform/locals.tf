locals {
  # Coursework-required topology
  master_vcpu    = 2
  master_ram_gb  = 8
  master_disk_gb = 40

  data_hosts   = 3
  data_vcpu    = 4
  data_ram_gb  = 16
  data_disk_gb = 128

  hours_per_month = 720

  # Example rates from README / Yandex pricing examples.
  # Keep overridable via variables so they can be updated without code changes.
  master_hourly = (
    local.master_vcpu * var.price_vcpu_hourly +
    local.master_ram_gb * var.price_ram_gb_hourly +
    local.master_disk_gb * var.price_network_hdd_gb_hourly
  )

  data_host_hourly = (
    local.data_vcpu * var.price_vcpu_hourly +
    local.data_ram_gb * var.price_ram_gb_hourly +
    local.data_disk_gb * var.price_network_hdd_gb_hourly
  )

  cluster_hourly_estimate  = local.master_hourly + (local.data_hosts * local.data_host_hourly)
  cluster_monthly_estimate = local.cluster_hourly_estimate * local.hours_per_month

  hdfs_total_gb                   = local.master_disk_gb + (local.data_hosts * local.data_disk_gb)
  hdfs_monthly_storage_estimate   = local.hdfs_total_gb * var.price_network_hdd_gb_hourly * local.hours_per_month
  object_storage_monthly_estimate = local.hdfs_total_gb * var.price_object_storage_standard_gb_monthly
  hdfs_vs_object_storage_ratio    = local.object_storage_monthly_estimate == 0 ? null : local.hdfs_monthly_storage_estimate / local.object_storage_monthly_estimate
}
