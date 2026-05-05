# MLOps ДЗ №7 — A/B валидация модели обнаружения мошенничества

Решение домашнего задания №7 курса MLOps от OTUS.
Расширяет hw6: к шагу обучения добавляется **шаг A/B валидации** со статистической значимостью (McNemar test + bootstrap CI).

## Что внутри

```
.
├── README.md
├── .gitignore
├── terraform/                              # standalone — копия hw6 на случай если hw6 снесён
│   ├── ...
│   └── cloud-init/mlflow.yaml.tpl
├── dags/
│   └── retrain_and_validate_dag.py         # 4 шага: create → train → validate → delete
└── scripts/
    ├── train_model.py                      # копия из hw6
    ├── validate_ab.py                      # NEW! A/B тест champion vs challenger
    └── install_mlflow_full.sh              # mlflow + scikit-learn + statsmodels
```

## Что сделано (по заданию)

| # | Что требовалось | Где |
|---|---|---|
| 1 | Managed Airflow | reuse hw6 либо `terraform/main.tf` |
| 2 | MLflow на отдельной ВМ + БД метаданных | reuse hw6 либо `terraform/cloud-init/mlflow.yaml.tpl` |
| 3 | **Стратегия валидации + код A/B теста** | `scripts/validate_ab.py` (см. ниже) |
| 4 | Шаг валидации в DAG | `dags/retrain_and_validate_dag.py` (3-й таск `run_validate_ab_job`) |
| 5 | Артефакты модели в S3 | через MLflow `--default-artifact-root s3://...` |
| 6 | Расписание | `schedule="0 */3 * * *"` (каждые 3 часа) |

---

# 🧠 Стратегия валидации (зачем McNemar + bootstrap)

В hw6 промоция в Production делалась тупо: «новый recall выше — повышаем». В hw7 это **статистическое решение**:

1. **Champion** = текущая Production-модель.
   **Challenger** = последняя зарегистрированная (но ещё не Production).
2. На **одной и той же** test-выборке (фикс seed=42) обе модели делают предсказания.
3. **McNemar test** на парных предсказаниях — проверяет, *статистически ли значимо* отличаются доли правильных предсказаний у двух моделей.
4. **Bootstrap (1000 итераций)** — даёт 95% доверительный интервал для разности `recall_chall − recall_champ`.
5. **Решение о промоции** = `True` ⟺ выполнено **всё**:
   - `recall_chall > recall_champ` (точечно лучше);
   - `p-value McNemar < 0.05` (статистически значимо);
   - нижняя граница bootstrap CI > 0 (доверительно лучше).

Если challenger **не победил статистически** — он автоматически уходит в `Archived`, в Production остаётся champion. Это защищает от выкатки худшей модели из-за случайной флуктуации.

Все эти величины (`mcnemar_pvalue`, `bootstrap_diff_recall_ci_low/high`, `champion_*`, `challenger_*`, `diff_*`, `promote_decision`) сохраняются в **MLflow run** в эксперименте `fraud_detection`.

---

# 🚀 Пошаговая инструкция

## Путь A — у тебя ЖИВА инфраструктура hw6 (рекомендуется)

Самый быстрый способ. Используем готовые Airflow + MLflow + S3 + SA из hw6.

### 1. Залить новые файлы в существующий S3 бакет hw6

```bash
# в .venv с awscli и профилем yc настроенным как в hw6
BUCKET=mlops-hw6-avkornev   # имя твоего hw6-бакета

aws s3 cp --endpoint-url=https://storage.yandexcloud.net --profile yc \
  scripts/validate_ab.py s3://$BUCKET/scripts/validate_ab.py

aws s3 cp --endpoint-url=https://storage.yandexcloud.net --profile yc \
  scripts/install_mlflow_full.sh s3://$BUCKET/scripts/install_mlflow_full.sh

aws s3 cp --endpoint-url=https://storage.yandexcloud.net --profile yc \
  dags/retrain_and_validate_dag.py s3://$BUCKET/dags/retrain_and_validate_dag.py
```

### 2. (Если Managed Airflow удалён) — поднять заново

Если ты делал partial destroy и снёс только Airflow, пересоздай его — terraform hw6 остался:
```bash
cd ../mlops-otus-hw6/terraform   # или твоя hw6 директория
terraform apply -auto-approve     # ~15 минут
```

Если Airflow жив — пропусти этот шаг.

### 3. Проверить Airflow Variables

Все 9 переменных из hw6 (`dp_sa_id`, `dp_subnet_id`, `dp_sg_id`, `dp_bucket`, `dp_zone`, `mlflow_tracking_uri`, `aws_access_key`, `aws_secret_key`, `dp_ssh_pubkey`) **уже** настроены — DAG hw7 использует те же.

### 4. Включить новый DAG `retrain_and_validate_fraud_model` в Airflow UI

Подожди 1 минуту после загрузки в S3 — он появится. Тоггл в On.

### 5. Trigger DAG

В UI кнопка ▶️ Trigger. Прогон ~30 минут (на 1 шаг больше чем в hw6: validate_ab).

### 6. Проверить MLflow

В experiment `fraud_detection` появится новый run с именем `ab_v<N>_vs_v<M>` и метриками:
- `champion_*`, `challenger_*` — метрики каждой модели;
- `diff_recall`, `diff_f1`, ... — разности;
- `mcnemar_pvalue`, `mcnemar_statistic` — статистический тест;
- `bootstrap_diff_recall_*` — доверительный интервал;
- `promote_decision` — 0 или 1.

Можешь открыть `tasteful-mouse-766` (твой run hw6) и сравнить с новым.

### 7. Скриншоты для README

В `images/` положи:
- `airflow_dag_4steps.png` — Graph view с 4 зелёными тасками
- `mlflow_ab_run.png` — открытый run `ab_v..._vs_v...` с таблицей метрик
- `mlflow_metrics_compare.png` — сравнение champion vs challenger метрик

---

## Путь B — поднять hw7 standalone (если hw6 уже снесён)

Если ты сделал полный destroy hw6 — поднимай hw7 заново.

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# заполни как в hw6 (yc_token, IDs, ssh_pubkey, bucket_name = mlops-hw7-...)
terraform init
terraform apply -auto-approve   # ~25 минут
```

Дальше как Путь A, шаги 1, 3-7. Но `BUCKET` будет уже `mlops-hw7-...`.

⚠️ Если у тебя **нет данных** в `s3://$BUCKET/cleaned/fraud_transactions/` — сгенерируй их через `scripts/generate_fraud_data.py` из hw6 и залей. И запусти `train_model.py` хотя бы **дважды**, чтобы у тебя в MLflow были и champion (Production), и challenger (None) — иначе A/B тесту нечего сравнивать.

---

# 📝 Шаблон отчёта для GitLab

```
ДЗ №7 выполнено.
Репозиторий: https://github.com/<логин>/mlops-otus-hw7

Что сделано:
1. ✅ Managed Airflow — переиспользована инфраструктура hw6.
2. ✅ MLflow Tracking Server на VM — переиспользована инфраструктура hw6,
   PostgreSQL для метаданных встроена на ту же VM (cloud-init).
3. ✅ Стратегия валидации:
     - hold-out 20% test set с фикс seed=42
     - сравниваются champion (Production) и challenger (latest)
     - McNemar test на парных предсказаниях (alpha=0.05)
     - Bootstrap 1000 итераций для 95% CI разности recall
   Код: scripts/validate_ab.py
4. ✅ В DAG retrain_and_validate_fraud_model добавлен шаг
   run_validate_ab_job (PySpark job, использует validate_ab.py).
5. ✅ Артефакты валидации (CSV с предсказаниями) и все метрики
   логируются в MLflow → S3 (s3://<bucket>/mlflow/).
6. ✅ Расписание DAG: 0 */3 * * *. Зелёный run подтверждён скриншотом.

Скриншоты: images/airflow_dag_4steps.png, images/mlflow_ab_run.png
```

---

# 🐛 Частые проблемы

## `ModuleNotFoundError: statsmodels` в Data Proc
init-action `install_mlflow_full.sh` не отработал. Проверь, что он в S3:
```bash
aws s3 ls --endpoint-url=https://storage.yandexcloud.net --profile yc \
  s3://$BUCKET/scripts/
```
И в DAG в `initialization_actions` указан `install_mlflow_full.sh`, **не** `install_mlflow.sh` из hw6.

## A/B тест: «нет Production-модели»
Скрипт сам промотирует первую попавшуюся модель в Production и выйдет. Запусти DAG ещё раз — теперь будет champion.

## `promote_decision = 0` всё время
Это **корректное** поведение, если challenger статистически неотличим от champion. Это и есть смысл валидации — НЕ выкатывать худшую/одинаковую модель. Чтобы получить promote_decision=1 — нужно реальное улучшение в обучении (увеличь `--num-trees` в DAG до 200 или `--max-depth` до 12).

---

# ❗ Удалить после сдачи

```bash
cd terraform
BUCKET=$(terraform output -raw bucket_name)
aws s3 rm s3://$BUCKET --recursive \
  --endpoint-url=https://storage.yandexcloud.net --profile yc
terraform destroy -auto-approve
```

Удачи!
