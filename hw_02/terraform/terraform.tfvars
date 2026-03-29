yc_token  = "<yc_token>"
cloud_id  = "<cloud_id>"
folder_id = "<folder_id>"

zone                  = "ru-central1-a"
environment           = "hw02"
bucket_name           = "avkornev-mlops-hw02-2026"
dataproc_cluster_name = "otus-mlops-dp"

# Restrict this to your own external IP whenever possible.Y
ssh_allowed_cidr = "1.1.1.1/32"

existing_network_id = "<existing_network_id>"
#existing_subnet_id  = "e9ba3ihf9846tcvfcma8"
network_cidr    = "10.200.0.0/24"
public_key_path = "/Users/xcore/.ssh/id_rsa.pub"

# The homework reviewer needs anonymous access to inspect the copied data.
public_bucket_read = true
enable_ui_proxy    = true
