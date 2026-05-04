# MLOps ДЗ №4 — Feature Store на Feast

Решение домашнего задания №4 курса MLOps от OTUS.

## Что внутри

```
.
├── README.md
├── requirements.txt
├── .gitignore
├── feature_repo/
│   ├── feature_store.yaml         # конфигурация (registry + online + offline store)
│   └── definitions.py             # 2 FeatureView + 1 OnDemandFeatureView
├── scripts/
│   └── generate_data.py           # генератор синтетических parquet
└── notebooks/
    └── feast_demo.ipynb           # offline + materialize + online retrieval
```

## Что сделано (по заданию)

| # | Что требовалось | Где |
|---|---|---|
| 1 | Создать **2 Feature View** | `feature_repo/definitions.py` — `driver_hourly_stats_fv`, `driver_trip_stats_fv` |
| 2 | Создать **1 on-demand Feature View** с трансформацией | `feature_repo/definitions.py` — `driver_efficiency_odfv` |
| 3 | **Ноутбук** с offline и online запросами | `notebooks/feast_demo.ipynb` |

---

```
ДЗ №4 выполнено.
Репозиторий: https://github.com/<логин>/mlops-otus-hw4

Что сделано:
1. 2 Feature View созданы (feature_repo/definitions.py):
   - driver_hourly_stats_fv (conv_rate, acc_rate, avg_daily_trips)
   - driver_trip_stats_fv (total_trips, total_distance_km, total_revenue, avg_rating)
2. 1 on-demand Feature View с трансформацией:
   - driver_efficiency_odfv — считает revenue_per_trip, distance_per_trip,
     effective_conv_score, is_top_driver на основе обеих базовых FV.
3. Ноутбук notebooks/feast_demo.ipynb демонстрирует:
   - get_historical_features() — offline retrieval для обучения
   - materialize_incremental() — заливка в online store
   - get_online_features() — online retrieval для инференса

Запуск:
  pip install -r requirements.txt
  python scripts/generate_data.py
  cd feature_repo && feast apply
  jupyter notebook notebooks/feast_demo.ipynb
```

