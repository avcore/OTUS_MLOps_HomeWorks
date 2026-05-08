"""Приёмочные тесты Fraud Detection API."""

VALID_TX = {
    "step":            100,
    "type":            "TRANSFER",
    "amount":          50_000.0,
    "nameOrig":        "C123456789",
    "oldbalanceOrg":   100_000.0,
    "newbalanceOrig":  50_000.0,
    "nameDest":        "M987654321",
    "oldbalanceDest":  0.0,
    "newbalanceDest":  50_000.0,
}

LIKELY_FRAUD_TX = {
    "step":            500,
    "type":            "TRANSFER",
    "amount":          800_000.0,         # очень крупная
    "nameOrig":        "C123",
    "oldbalanceOrg":   800_000.0,
    "newbalanceOrig":  0.0,
    "nameDest":        "C456",
    "oldbalanceDest":  0.0,
    "newbalanceDest":  0.0,                 # деньги «исчезли»
}


def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_version_returns_string(client):
    r = client.get("/version")
    assert r.status_code == 200
    assert "api_version" in r.json()


def test_predict_valid_returns_200(client):
    r = client.post("/predict", json=VALID_TX)
    assert r.status_code == 200
    body = r.json()
    assert body["is_fraud"] in (0, 1)
    assert 0.0 <= body["probability"] <= 1.0
    assert body["inference_ms"] > 0


def test_predict_response_schema(client):
    r = client.post("/predict", json=VALID_TX)
    body = r.json()
    for key in ("is_fraud", "probability", "api_version", "inference_ms"):
        assert key in body, f"missing key: {key}"


def test_predict_missing_field_returns_422(client):
    r = client.post("/predict", json={"foo": "bar"})
    assert r.status_code == 422


def test_predict_negative_amount_rejected(client):
    bad = dict(VALID_TX, amount=-100.0)
    r = client.post("/predict", json=bad)
    assert r.status_code == 422


def test_predict_unknown_type_does_not_crash(client):
    bad = dict(VALID_TX, type="MAGIC_TYPE_42")
    r = client.post("/predict", json=bad)
    # type — обычная строка, неизвестное значение → type_idx=0, без падения
    assert r.status_code == 200


def test_predict_smoke_high_amount(client):
    """Большая подозрительная транзакция — модель не должна падать."""
    r = client.post("/predict", json=LIKELY_FRAUD_TX)
    assert r.status_code == 200
    assert r.json()["probability"] >= 0.0
