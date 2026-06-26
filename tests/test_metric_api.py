from fastapi.testclient import TestClient

from service.main import app

client = TestClient(app)


def test_metric_endpoint_returns_data_and_meta():
    r = client.get("/api/metric/sustainer_mrr")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["id"] == "sustainer_mrr"
    assert "data" in body


def test_metric_endpoint_unknown_is_404():
    r = client.get("/api/metric/nope")
    assert r.status_code == 404


def test_metric_endpoint_bad_brand_is_400():
    r = client.get("/api/metric/streaming_tlh", params={"brand": "NOPE"})
    assert r.status_code == 400
