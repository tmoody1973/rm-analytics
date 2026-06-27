"""Tests for the catalog endpoints: GET /api/metrics and GET /api/schema.

/api/metrics — no DB call needed; returns the in-memory REGISTRY.
/api/schema  — needs a live DATABASE_URL; skipped when unavailable.
               The funraise-exclusion assertion is a hard guard even on live.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from service.main import app

client = TestClient(app)

_ENV_PATH = Path.home() / ".radio-milwaukee" / ".env"


def _db_available() -> bool:
    if os.environ.get("DATABASE_URL"):
        return True
    if _ENV_PATH.exists():
        from dotenv import dotenv_values
        return bool(dotenv_values(_ENV_PATH).get("DATABASE_URL"))
    return False


# ----------------------------------------------------------------- /api/metrics ---

class TestListMetrics:
    def test_returns_200(self):
        r = client.get("/api/metrics")
        assert r.status_code == 200

    def test_returns_list(self):
        r = client.get("/api/metrics")
        body = r.json()
        assert isinstance(body, list)

    def test_minimum_entry_count(self):
        r = client.get("/api/metrics")
        body = r.json()
        assert len(body) >= 12, f"expected ≥12 metrics, got {len(body)}"

    def test_each_entry_has_required_fields(self):
        r = client.get("/api/metrics")
        body = r.json()
        required = {"id", "name", "description", "unit", "source"}
        for entry in body:
            missing = required - entry.keys()
            assert not missing, f"metric {entry.get('id')!r} missing fields: {missing}"

    def test_ids_are_non_empty_strings(self):
        r = client.get("/api/metrics")
        for entry in r.json():
            assert isinstance(entry["id"], str) and entry["id"].strip()

    def test_sources_are_non_empty_strings(self):
        r = client.get("/api/metrics")
        for entry in r.json():
            assert isinstance(entry["source"], str) and entry["source"].strip(), (
                f"metric {entry['id']!r} has empty source"
            )

    def test_known_streaming_metric_present(self):
        r = client.get("/api/metrics")
        ids = {e["id"] for e in r.json()}
        assert "streaming_tlh" in ids

    def test_no_funraise_in_exposed_ids(self):
        """Metric ids must not accidentally expose raw funraise table names."""
        r = client.get("/api/metrics")
        # We allow funraise as a *source* citation on aggregate metrics
        # (that's fine — it's a label, not a queryable path), but no metric
        # id itself should contain the word funraise.
        for entry in r.json():
            assert "funraise" not in entry["id"].lower(), (
                f"metric id {entry['id']!r} unexpectedly contains 'funraise'"
            )


# ----------------------------------------------------------------- /api/schema ---

class TestGetSchema:
    @pytest.mark.skipif(not _db_available(), reason="DATABASE_URL not set")
    def test_returns_200(self):
        r = client.get("/api/schema")
        assert r.status_code == 200

    @pytest.mark.skipif(not _db_available(), reason="DATABASE_URL not set")
    def test_returns_list(self):
        r = client.get("/api/schema")
        body = r.json()
        assert isinstance(body, list), "expected a JSON array"

    @pytest.mark.skipif(not _db_available(), reason="DATABASE_URL not set")
    def test_each_entry_has_required_fields(self):
        r = client.get("/api/schema")
        for entry in r.json():
            assert "schema" in entry, f"missing 'schema' in {entry}"
            assert "table" in entry, f"missing 'table' in {entry}"
            assert "columns" in entry, f"missing 'columns' in {entry}"
            assert isinstance(entry["columns"], list)

    @pytest.mark.skipif(not _db_available(), reason="DATABASE_URL not set")
    def test_columns_have_name_and_type(self):
        r = client.get("/api/schema")
        for entry in r.json():
            for col in entry["columns"]:
                assert "name" in col, f"column missing 'name' in {entry['schema']}.{entry['table']}"
                assert "type" in col, f"column missing 'type' in {entry['schema']}.{entry['table']}"

    @pytest.mark.skipif(not _db_available(), reason="DATABASE_URL not set")
    def test_wms_schema_present(self):
        r = client.get("/api/schema")
        schemas = {e["schema"] for e in r.json()}
        assert "wms" in schemas, f"wms not found in schemas: {schemas}"

    @pytest.mark.skipif(not _db_available(), reason="DATABASE_URL not set")
    def test_nielsen_schema_present(self):
        r = client.get("/api/schema")
        schemas = {e["schema"] for e in r.json()}
        assert "nielsen" in schemas, f"nielsen not found in schemas: {schemas}"

    @pytest.mark.skipif(not _db_available(), reason="DATABASE_URL not set")
    def test_funraise_schema_present(self):
        """funraise (de-identified donor data) is now exposed so the assistant
        can query it. The endpoint is gated behind INTERNAL_API_TOKEN."""
        r = client.get("/api/schema")
        schemas = {e["schema"] for e in r.json()}
        assert "funraise" in schemas, f"funraise not found in schemas: {schemas}"

    @pytest.mark.skipif(not _db_available(), reason="DATABASE_URL not set")
    def test_funraise_pii_columns_not_value_enumerated(self):
        """CRITICAL: funraise tables may appear, but PII-adjacent column VALUES
        (email hash, city, postal, state, address) must never be enumerated."""
        r = client.get("/api/schema")
        pii_bits = ("email", "city", "postal", "zip", "address", "state", "phone")
        for entry in r.json():
            if entry["schema"] != "funraise":
                continue
            for col in entry["columns"]:
                if any(bit in col["name"].lower() for bit in pii_bits):
                    assert "values" not in col, (
                        f"funraise.{entry['table']}.{col['name']} enumerated PII values"
                    )

    def test_schema_catalog_includes_funraise_in_allowed_set(self):
        """Unit-level guard: catalog_api._ALLOWED_SCHEMAS now includes funraise."""
        from service.catalog_api import _ALLOWED_SCHEMAS
        assert "funraise" in _ALLOWED_SCHEMAS, (
            "funraise must be in _ALLOWED_SCHEMAS for the assistant to query it"
        )

    @pytest.mark.skipif(not _db_available(), reason="DATABASE_URL not set")
    def test_wms_fact_monthly_cume_has_columns(self):
        """Spot-check a known table has the columns we expect."""
        r = client.get("/api/schema")
        entries = {
            (e["schema"], e["table"]): e["columns"]
            for e in r.json()
        }
        key = ("wms", "fact_monthly_cume")
        assert key in entries, f"wms.fact_monthly_cume missing from catalog"
        col_names = {c["name"] for c in entries[key]}
        assert "station_code" in col_names
        assert "tlh" in col_names

    @pytest.mark.skipif(not _db_available(), reason="DATABASE_URL not set")
    def test_result_is_sorted(self):
        """Schema entries should be returned sorted by schema then table."""
        r = client.get("/api/schema")
        body = r.json()
        pairs = [(e["schema"], e["table"]) for e in body]
        assert pairs == sorted(pairs), "catalog not sorted by (schema, table)"

    def test_enrich_blocks_funraise_pii_columns(self):
        """Unit: _enrich_distinct_values must NOT enumerate PII columns even on
        funraise — it returns early before issuing any query."""
        from service.catalog_api import _enrich_distinct_values
        for name in ("email_sha256", "city", "postal_code", "state"):
            col = {"name": name, "type": "text"}
            # cur=None proves no DB query is attempted for these columns.
            _enrich_distinct_values(None, "funraise", "dim_supporters", col)
            assert "values" not in col, f"{name} should not be value-enumerated"

    def test_enrich_allows_funraise_dimension_column(self):
        """Unit: a curated dimension column (designation) IS enumerated."""
        from service.catalog_api import _enrich_distinct_values

        class _FakeCur:
            def execute(self, *a, **k):
                pass
            def fetchall(self):
                return [{"v": "Foundations", "n": 5}, {"v": "Membership", "n": 3}]

        col = {"name": "designation", "type": "text"}
        _enrich_distinct_values(_FakeCur(), "funraise", "fact_transactions", col)
        assert col.get("values") == ["Foundations", "Membership"]
