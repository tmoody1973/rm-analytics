"""Svix webhook signature verification.

AgentMail signs every webhook with Svix headers (svix-id, svix-timestamp,
svix-signature). We verify against the secret produced when the webhook was
registered (starts with `whsec_`).

Raises svix.webhooks.WebhookVerificationError on tampering / replay.
"""
from __future__ import annotations

import os

from svix.webhooks import Webhook, WebhookVerificationError


_SECRET_ENV = "AGENTMAIL_WEBHOOK_SECRET"
_SHEET_SECRET_ENV = "SHEET_SYNC_SECRET"


def verify_agentmail(raw_body: bytes, headers: dict[str, str]) -> None:
    """Verify a Svix-signed AgentMail webhook. Raises on failure."""
    secret = os.environ.get(_SECRET_ENV)
    if not secret:
        raise RuntimeError(f"{_SECRET_ENV} not set")
    Webhook(secret).verify(raw_body, headers)


def verify_sheet_secret(headers: dict[str, str]) -> None:
    """Verify the shared secret on a Google Sheets 'Sync to Neon' POST.

    The Apps Script sends `X-RM-Sheet-Secret`; we compare it to SHEET_SYNC_SECRET.
    `headers` keys must be lowercased by the caller. Raises on mismatch/missing.
    """
    expected = os.environ.get(_SHEET_SECRET_ENV)
    if not expected:
        raise RuntimeError(f"{_SHEET_SECRET_ENV} not set")
    got = headers.get("x-rm-sheet-secret")
    if not got or got != expected:
        raise WebhookVerificationError("invalid or missing sheet secret")


__all__ = ["verify_agentmail", "verify_sheet_secret", "WebhookVerificationError"]
