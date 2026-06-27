"""Integration tests for the shared-secret gate on assistant tool endpoints.

The autouse bypass (conftest) is popped here so we hit the real dependency.
Gated: /api/metric, /api/metrics, /api/schema, /api/ask-sql, /api/newsletter-content.
Ungated: /api/dashboard (browser aggregate path), /health, /webhook/*.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from service.internal_auth import require_internal_token
from service.main import app

TOKEN = "test-internal-token-value"
client = TestClient(app)


@pytest.fixture
def real_auth(monkeypatch):
    """Remove the autouse bypass and configure a real server token."""
    app.dependency_overrides.pop(require_internal_token, None)
    monkeypatch.setenv("INTERNAL_API_TOKEN", TOKEN)
    yield


@pytest.mark.parametrize("path", [
    "/api/metrics",
    "/api/metric/streaming_tlh",
    "/api/newsletter-content/abc123",
])
def test_gated_get_returns_401_without_token(real_auth, path):
    assert client.get(path).status_code == 401


def test_gated_schema_returns_401_without_token(real_auth):
    assert client.get("/api/schema").status_code == 401


def test_ask_sql_returns_401_without_token(real_auth):
    r = client.post("/api/ask-sql", json={"sql": "SELECT 1"})
    assert r.status_code == 401


def test_gated_endpoint_passes_with_correct_token(real_auth):
    # /api/metrics needs no DB; with the right token the gate lets it through.
    r = client.get("/api/metrics", headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 200


def test_gated_endpoint_401_with_wrong_token(real_auth):
    r = client.get("/api/metrics", headers={"X-Internal-Token": "wrong"})
    assert r.status_code == 401


def test_dashboard_is_not_gated(real_auth):
    # Aggregate browser path — must never 401 from the internal-token gate.
    assert client.get("/api/dashboard").status_code != 401


def test_health_is_not_gated(real_auth):
    assert client.get("/health").status_code == 200
