"""Shared test fixtures.

The assistant tool endpoints are gated behind require_internal_token. Existing
endpoint tests predate that gate and call the routes without a token, so by
default we override the dependency to a no-op. Tests that specifically exercise
the gate (tests/test_endpoint_gating.py) pop this override to see the real 401.
"""
from __future__ import annotations

import pytest

from service.internal_auth import require_internal_token
from service.main import app


@pytest.fixture(autouse=True)
def _bypass_internal_auth():
    app.dependency_overrides[require_internal_token] = lambda: None
    yield
    app.dependency_overrides.pop(require_internal_token, None)
