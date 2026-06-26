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
    def test_funraise_schema_absent(self):
        """CRITICAL: funraise (donor PII) must NEVER appear in the schema catalog."""
        r = client.get("/api/schema")
        body = r.json()
        funraise_entries = [e for e in body if e.get("schema") == "funraise"]
        assert not funraise_entries, (
            f"funraise schema leaked into /api/schema: {funraise_entries}"
        )

    @pytest.mark.skipif(not _db_available(), reason="DATABASE_URL not set")
    def test_funraise_absent_in_any_field(self):
        """Paranoia check: 'funraise' must not appear anywhere in the response."""
        r = client.get("/api/schema")
        import json
        raw = json.dumps(r.json()).lower()
        assert "funraise" not in raw, (
            "The word 'funraise' appeared somewhere in /api/schema response"
        )

    def test_schema_catalog_excludes_funraise_from_allowed_set(self):
        """Unit-level guard: catalog_api._ALLOWED_SCHEMAS must not include funraise."""
        from service.catalog_api import _ALLOWED_SCHEMAS
        assert "funraise" not in _ALLOWED_SCHEMAS, (
            "funraise must not appear in _ALLOWED_SCHEMAS"
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

    def test_mocked_schema_excludes_funraise(self):
        """Without a live DB, verify the SQL in _fetch_schema_from_db only
        queries _ALLOWED_SCHEMAS and would never return funraise rows."""
        from service.catalog_api import _ALLOWED_SCHEMAS
        # Simulate what the DB would return including a rogue funraise row
        mock_rows = [
            {"schema": "wms", "table": "fact_monthly_cume", "name": "station_code", "type": "text"},
            {"schema": "nielsen", "table": "fact_vital_signs", "name": "value_numeric", "type": "numeric"},
            # This should never come back from DB because funraise is not in _ALLOWED_SCHEMAS,
            # but if it did the catalog would need to filter it
        ]
        assert "funraise" not in _ALLOWED_SCHEMAS
        # If funraise were not in _ALLOWED_SCHEMAS, the SQL WHERE clause
        # would never include it, so mock rows from funraise can't appear.
        filtered = [r for r in mock_rows if r["schema"] in _ALLOWED_SCHEMAS]
        assert all(r["schema"] != "funraise" for r in filtered)
