"""Unit tests for the shared-secret gate on the assistant tool endpoints.

require_internal_token is a FastAPI dependency: it compares the X-Internal-Token
header to the INTERNAL_API_TOKEN env var with a constant-time compare, fails
closed (503) when the server isn't configured, and 401s on a missing/wrong token.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from service.internal_auth import require_internal_token

TOKEN = "s3cr3t-internal-token-value"


def test_passes_when_token_matches(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", TOKEN)
    # No exception, returns None.
    assert require_internal_token(x_internal_token=TOKEN) is None


def test_401_when_token_missing(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", TOKEN)
    with pytest.raises(HTTPException) as exc:
        require_internal_token(x_internal_token=None)
    assert exc.value.status_code == 401


def test_401_when_token_wrong(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", TOKEN)
    with pytest.raises(HTTPException) as exc:
        require_internal_token(x_internal_token="not-the-token")
    assert exc.value.status_code == 401


def test_fails_closed_when_env_unset(monkeypatch):
    monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    with pytest.raises(HTTPException) as exc:
        require_internal_token(x_internal_token=TOKEN)
    assert exc.value.status_code == 503
