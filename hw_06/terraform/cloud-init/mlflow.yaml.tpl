#cloud-config
# Cloud-init для виртуальной машины MLflow Tracking Server.
# - устанавливает Python + pip + PostgreSQL
# - создаёт БД `mlflow` и пользователя `mlflow`
# - ставит mlflow + boto3 + psycopg2 в venv
# - настраивает systemd unit и стартует сервер на 0.0.0.0:5000
#
# Все переменные подставляет Terraform через templatefile().

users:
  - name: ubuntu
    sudo: ALL=(ALL) NOPASSWD:ALL
    ssh_authorized_keys:
      - "${ssh_pubkey}"

package_update: true
package_upgrade: false
packages:
  - python3
  - python3-pip
  - python3-venv
  - postgresql
  - postgresql-contrib

write_files:
  - path: /etc/systemd/system/mlflow.service
    permissions: "0644"
    content: |
      [Unit]
      Description=MLflow Tracking Server
      After=network.target postgresql.service
      Requires=postgresql.service

      [Service]
      Type=simple
      User=ubuntu
      Group=ubuntu
      Environment=AWS_ACCESS_KEY_ID=${aws_access_key}
      Environment=AWS_SECRET_ACCESS_KEY=${aws_secret_key}
      Environment=MLFLOW_S3_ENDPOINT_URL=https://storage.yandexcloud.net
      ExecStart=/opt/mlflow/venv/bin/mlflow server \
        --backend-store-uri postgresql+psycopg2://mlflow:${pg_password}@127.0.0.1:5432/mlflow \
        --default-artifact-root s3://${bucket}/mlflow/ \
        --host 0.0.0.0 \
        --port 5000 \
        --workers 2
      Restart=always
      RestartSec=10

      [Install]
      WantedBy=multi-user.target

  - path: /opt/mlflow/setup.sh
    permissions: "0755"
    content: |
      #!/bin/bash
      set -euxo pipefail

      # 1. PostgreSQL: создаём БД и пользователя
      sudo -u postgres psql <<EOF
      CREATE USER mlflow WITH PASSWORD '${pg_password}';
      CREATE DATABASE mlflow OWNER mlflow;
      GRANT ALL PRIVILEGES ON DATABASE mlflow TO mlflow;
      ALTER USER mlflow WITH SUPERUSER;
      EOF

      # 2. PostgreSQL: разрешаем подключения с localhost
      PG_VERSION=$(ls /etc/postgresql/)
      echo "host  all  all  127.0.0.1/32  md5" | sudo tee -a /etc/postgresql/$PG_VERSION/main/pg_hba.conf
      sudo systemctl restart postgresql

      # 3. Python venv + MLflow
      sudo mkdir -p /opt/mlflow
      sudo chown -R ubuntu:ubuntu /opt/mlflow
      python3 -m venv /opt/mlflow/venv
      /opt/mlflow/venv/bin/pip install --upgrade pip
      /opt/mlflow/venv/bin/pip install \
          "mlflow==2.16.2" \
          "boto3" \
          "psycopg2-binary"

      # 4. Запускаем сервис
      sudo systemctl daemon-reload
      sudo systemctl enable mlflow.service
      sudo systemctl start mlflow.service

      echo "MLflow готов на :5000" > /home/ubuntu/mlflow_ready.txt
      chown ubuntu:ubuntu /home/ubuntu/mlflow_ready.txt

runcmd:
  - bash /opt/mlflow/setup.sh 2>&1 | tee /var/log/mlflow_setup.log
