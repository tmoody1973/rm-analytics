"""Shared-secret gate for the assistant's tool endpoints (funraise-unblock).

The Fly service tool endpoints (/api/ask-sql, /api/metric, /api/metrics,
/api/schema, /api/newsletter-content) are called server-to-server by the
Clerk-gated Vercel CopilotKit function — never by a browser directly. Once
the funraise (donor) schema is reachable via /api/ask-sql, these endpoints
must NOT be openly callable. require_internal_token enforces a shared secret
(INTERNAL_API_TOKEN) sent as the X-Internal-Token header.

Fails closed: if INTERNAL_API_TOKEN is not configured on the server, every
gated request is rejected (503) rather than silently allowed.
"""
from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException

_TOKEN_ENV = "INTERNAL_API_TOKEN"


def require_internal_token(
    x_internal_token: str | None = Header(default=None),
) -> None:
    """FastAPI dependency: allow the request only if X-Internal-Token matches
    INTERNAL_API_TOKEN. 503 if the server has no token configured (fail closed),
    401 on a missing or wrong token. Constant-time compare avoids leaking the
    secret via response timing.
    """
    expected = os.environ.get(_TOKEN_ENV)
    if not expected:
        raise HTTPException(status_code=503, detail="internal auth not configured")
    if not x_internal_token or not hmac.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=401, detail="invalid or missing internal token")


__all__ = ["require_internal_token"]
