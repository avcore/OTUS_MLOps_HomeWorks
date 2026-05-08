# ---- Stage 1: build dependencies ---------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build
COPY api/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- Stage 2: runtime --------------------------------------------------
FROM python:3.11-slim

LABEL org.opencontainers.image.title="fraud-detection-api"
LABEL org.opencontainers.image.description="MLOps HW9 — FastAPI fraud detector"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH

WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY api/ ./api/

# Тренируем dummy-модель ПРИ СБОРКЕ — внутри контейнера будет model.pkl
RUN python -m api.train_local

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
