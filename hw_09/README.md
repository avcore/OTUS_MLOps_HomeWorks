# MLOps ДЗ №9 — REST API + Docker + Kubernetes + CI/CD

Решение домашнего задания №9 курса MLOps от OTUS.

## Архитектура

```
GitHub repo (push в main)
    │
    ├── .github/workflows/test.yml         pytest (api/tests/)
    │       │   pass
    │       ▼
    ├── .github/workflows/build-push.yml   docker build → push в Yandex CR
    │       │   pass
    │       ▼
    └── .github/workflows/deploy.yml       (бонус) kubectl apply k8s/*

                                                    │
                                                    ▼
                            ┌───────────────────────────────────────┐
                            │  Yandex Container Registry            │
                            │  cr.yandex/<id>/fraud-api:<sha>       │
                            └───────────────────────────────────────┘
                                                    │
                                                    │ image pull
                                                    ▼
                            ┌───────────────────────────────────────┐
                            │  Yandex Managed Kubernetes (3 worker)  │
                            │                                        │
                            │  Namespace: fraud                      │
                            │  Deployment: fraud-api (2 replicas)    │
                            │  Service: type=LoadBalancer  port=80   │
                            └───────────────────────────────────────┘
                                                    │
                                                    │ public IP
                                                    ▼
                            curl http://<EXTERNAL_IP>/predict
```

## Что внутри

```
.
├── README.md
├── .gitignore
├── .dockerignore
├── Dockerfile                          # multi-stage: builder + runtime
├── api/
│   ├── __init__.py
│   ├── main.py                         # FastAPI: /health, /version, /predict
│   ├── model.py                        # FraudDetector wrapper
│   ├── train_local.py                  # обучение dummy RF на синтетике
│   ├── requirements.txt
│   └── tests/
│       ├── conftest.py
│       └── test_api.py                 # 8 pytest тестов
├── k8s/
│   ├── namespace.yaml
│   ├── deployment.yaml
│   └── service.yaml                    # LoadBalancer
├── terraform/                          # K8s cluster + Container Registry
│   ├── provider.tf
│   ├── variables.tf
│   ├── main.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
└── .github/workflows/
    ├── test.yml                        # на push: pytest
    ├── build-push.yml                  # на main: build + push в YCR
    └── deploy.yml                      # бонус: kubectl apply
```

## Что сделано (по заданию)

| # | Что требовалось | Где |
|---|---|---|
| 1 | REST API | `api/main.py` — FastAPI с `/health`, `/version`, `/predict` |
| 2 | CI/CD с тестами и сборкой | `.github/workflows/{test,build-push}.yml` |
| 3 | k8s манифесты | `k8s/{namespace,deployment,service}.yaml` |
| 4 | K8s кластер 3 узла в YC | `terraform/main.tf` ресурс `yandex_kubernetes_cluster` + `node_group` |
| 5 | Запустить и тестировать публичный API | `kubectl apply` → `curl <EXTERNAL_IP>/predict` |
| 6 | (бонус) автодеплой в k8s | `.github/workflows/deploy.yml` |

---

```
ДЗ №9 выполнено.

Что сделано:
1.  REST API на FastAPI (api/main.py): эндпоинты /health, /version, /predict.
   8 unit-тестов в api/tests/test_api.py.
2.  CI/CD в GitHub Actions:
   - test.yml — pytest на каждый push (gate)
   - build-push.yml — на main: docker build → push в Yandex Container Registry
   - deploy.yml — на main: kubectl apply манифестов (бонус)
3.  K8s манифесты: namespace + deployment (2 replicas) + service (LoadBalancer).
4.  K8s cluster с 3 worker-нодами развёрнут через terraform/main.tf
   (resource yandex_kubernetes_cluster + yandex_kubernetes_node_group fixed_scale 3).
5.  Сервис запущен в k8s, доступен по публичному IP, протестирован curl-ом.
6.  (бонус) Автодеплой в k8s через .github/workflows/deploy.yml — срабатывает
   после успешного build-push.

Скриншоты: images/01 ... images/05
```
