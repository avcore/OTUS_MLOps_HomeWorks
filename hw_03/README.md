# MLOps ДЗ №3 — Анализ качества и очистка датасета мошеннических финансовых операций

Репозиторий с решением домашнего задания №3 курса MLOps от OTUS.

## Что внутри

```
.
├── README.md                  # этот файл
├── terraform/                 # инфраструктура в Yandex Cloud
│   ├── provider.tf
│   ├── variables.tf
│   ├── main.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
├── scripts/
│   └── clean_data.py          # PySpark-скрипт очистки (запускается извне)
└── notebooks/
    └── analysis.ipynb         # Jupyter-ноутбук с анализом качества данных
```

## Точка доступа к bucket с очищенными данными

bucket_endpoint = "https://storage.yandexcloud.net/avkornev-mlops-hw03-2026/"
bucket_name = "avkornev-mlops-hw03-2026"
cluster_id = "c9q5k869ma86v5gt35m2"
cluster_name = "mlops-hw3-spark"
service_account_id = "ajeltk0hh7igbmv5fv2i"

Bucket настроен на публичное чтение (см. `terraform/main.tf`, ресурс `yandex_storage_bucket`, блок `acl = "public-read"`).

```
ДЗ №3 выполнено.
Репозиторий: https://github.com/<логин>/mlops-otus-hw3

Что сделано:
1. Сервисный аккаунт mlops-hw3-sa создан, выданы роли:
   storage.editor, dataproc.agent, dataproc.provisioner, vpc.user, monitoring.viewer.
2. Bucket `mlops-otus-hw3-edit-2026` создан, публичное чтение включено.
   Endpoint: https://storage.yandexcloud.net/mlops-otus-hw3-edit-2026/
3. Кластер Yandex Data Processing создан Terraform-ом:
   master  s3-c2-m8  / 40 GB
   data    s3-c4-m16 / 3 хоста / 128 GB
4. Анализ данных выполнен в Jupyter (см. notebooks/analysis.ipynb).
   Найдены 4 типа проблем:
   - пропуски (NULL) в nameDest и amount
   - дубликаты строк
   - отрицательные суммы транзакций
   - нарушение балансового тождества oldbalance - newbalance != amount
5. Скрипт очистки scripts/clean_data.py — запускается извне через
   `yc dataproc job create-pyspark` (см. README, шаг 6).
6. Очищенные данные сохранены в parquet:
   s3://mlops-otus-hw3-edit-2026/cleaned/fraud_transactions/
7. Kanban в GitHub Projects обновлён.
8. Кластер удалён через terraform destroy.
```

---

## Обнаруженные проблемы качества (минимум 3 — у нас 4)

| # | Тип проблемы | Колонки | Как обрабатывается скриптом |
|---|---|---|---|
| 1 | Пропущенные значения (NULL) | `amount`, `nameDest`, `oldbalanceOrg` | Удаление строк с NULL в ключевых полях |
| 2 | Дубликаты | все | `dropDuplicates()` |
| 3 | Невалидные значения | `amount < 0`, `type` не в списке допустимых | Фильтрация |
| 4 | Логическая несогласованность баланса | `oldbalanceOrg - newbalanceOrig != amount` (с допуском 0.01) | Фильтрация + флаг `balance_mismatch` для аналитики |

Дополнительно: приведение типов (`step:int`, `amount:double`), trim строковых колонок.
