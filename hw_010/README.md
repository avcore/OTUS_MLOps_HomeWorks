# MLOps ДЗ №10 — Production развёртывание + Prometheus/Grafana + Alerting

Решение домашнего задания №10 курса MLOps от OTUS.
Расширяет hw9: добавляет HPA (4–6 реплик), мониторинг через kube-prometheus-stack, алерты в AlertManager, имитацию DDoS через стресс-тест.

## Архитектура

```
                ┌──────────────────────────────────────────────────┐
                │  Yandex Managed Kubernetes (3 worker nodes)      │
                │                                                   │
                │  ┌────────────────┐    ┌──────────────────────┐  │
                │  │  ns: fraud     │    │  ns: monitoring      │  │
                │  │                │    │                      │  │
                │  │  Deployment    │◄───┤  ServiceMonitor       │  │
                │  │  fraud-api     │    │  /metrics             │  │
                │  │  replicas: 4-6 │    │                      │  │
                │  │                │    │  Prometheus           │  │
                │  │  HPA           │◄───┤  ── собирает метрики ─┤  │
                │  │  CPU > 70%     │    │                      │  │
                │  │  → scale up    │    │  AlertManager         │  │
                │  │                │    │  ── шлёт email ───────┤  │
                │  │                │    │                      │  │
                │  │  Service       │    │  Grafana              │  │
                │  │  LoadBalancer  │    │  (LoadBalancer)       │  │
                │  └────────────────┘    └──────────────────────┘  │
                │           │                       │               │
                │  ┌────────────────┐    ┌──────────────────────┐  │
                │  │  ns: airflow   │    │  PrometheusRule       │  │
                │  │  Airflow Web   │    │  FraudApiSaturated... │  │
                │  │  + Scheduler   │    │  (6 реплик и CPU>80%  │  │
                │  │  (DAGs из git) │    │   уже 5 минут)        │  │
                │  └────────────────┘    └──────────────────────┘  │
                └──────────────────────────────────────────────────┘
                            ▲
                            │
                ┌───────────┴────────────┐
                │  load_test/stress.py    │
                │  имитация DDoS:         │
                │  python stress.py       │
                │    --rps 300            │
                │    --duration 600       │
                └────────────────────────┘
```

## Что внутри

```
.
├── README.md
├── .gitignore
├── k8s/
│   ├── namespace.yaml
│   ├── deployment.yaml          # 4 replicas, requests=200m CPU
│   ├── hpa.yaml                 # min=4, max=6, по CPU 70%
│   ├── service.yaml             # LoadBalancer
│   ├── service-monitor.yaml     # для Prometheus scraping
│   └── alert-rules.yaml         # PrometheusRule с алертами
├── helm/
│   ├── prometheus-values.yaml   # values для kube-prometheus-stack
│   └── airflow-values.yaml      # values для apache-airflow chart
├── load_test/
│   ├── stress.py                # async load tester
│   └── requirements.txt
└── dags/
    └── .placeholder             # сюда копировать DAG'и из hw7 (Airflow в k8s их подхватит из git)
```

## Что сделано (по заданию)

| # | Что требовалось | Где |
|---|---|---|
| 1 | Deployment 4–6 реплик с авто-масштабированием | `k8s/deployment.yaml` (replicas=4) + `k8s/hpa.yaml` (min=4, max=6) |
| 2 | Airflow в K8s + Git DAG'и | `helm install airflow apache-airflow/airflow -f helm/airflow-values.yaml` |
| 3 | Prometheus + Grafana | `helm install kube-prometheus-stack -f helm/prometheus-values.yaml` |
| 4 | Алерт при 6 репликах + CPU > 80% × 5 мин | `k8s/alert-rules.yaml` rule `FraudApiSaturatedAtMaxReplicas` |
| 5 | Имитация атаки до срабатывания алерта | `load_test/stress.py --rps 300 --duration 600` |


```
ДЗ №10 выполнено.
Репозиторий: https://github.com/<логин>/mlops-otus-hw10

Что сделано:
1.  Deployment fraud-api в k8s, 4 реплики стартовых,
   HorizontalPodAutoscaler min=4 max=6 (k8s/hpa.yaml).
   Скейлится по CPU > 70%.
2.  Airflow развёрнут в кластере через Helm chart apache-airflow/airflow,
   DAG'и подтягиваются из git (gitSync), webserver через LoadBalancer.
3.  Prometheus + Grafana через kube-prometheus-stack helm chart.
   ServiceMonitor для fraud-api, дашборды Kubernetes / Pods из коробки.
4.  AlertManager: алерт FraudApiSaturatedAtMaxReplicas срабатывает
   при условии "6 реплик AND средний CPU > 80% в течение 5 минут".
   Уведомление через email_configs в alertmanager.config.
5.  Имитация атаки: load_test/stress.py с RPS=300, duration=600
   успешно поднимает кластер до 6 реплик и через 5 минут CPU > 80%
   срабатывает алерт.

Скриншоты: выполнение/*
```


## Покрытие пунктов задания

| Пункт задания | Доказывают | Что видно |
|---|---|---|
| **1. HPA 4..6 реплик** | `scr8` | `kubectl get hpa,deployment,pods` — `REPLICAS 6/6`, `MINPODS 4`, `MAXPODS 6`, 6 подов в `Running` |
| **2. Airflow в k8s + DAG из git** | `scr2`, `scr3`, `scr4`, `scr5` | Главная Airflow с runs-статистикой; список DAG'ов (`retrain_fraud_model_lite` + `retrain_and_validate_fraud_model`); успешные ручные запуски |
| **3. Prometheus + Grafana** | `scr10`–`scr25`, `scr26`, `scr27` | Десятки Grafana-дашбордов по разным неймспейсам (fraud, monitoring, kube-system, airflow); Prometheus Alerts UI с группой `fraud-api` |
| **4. Алерт админу (6 реплик + CPU >80% × 5 min)** | `scr1`, `scr6`, `scr9`, `scr26`, `scr28`, `scr30` | PrometheusRule в YAML; AlertManager UI с активными `FraudApiPodHighCpu` (warning), `FraudApiAtMaxReplicas` (info); **скрин Telegram с пришедшими уведомлениями** |
| **5. Имитация атаки** | `scr7`, `scr29`, `scr11`, `scr22`, `scr23` | `stress.py` льёт RPS на API; Grafana с пиками трафика (Network bandwidth/packets — отчётливо видны всплески) |
