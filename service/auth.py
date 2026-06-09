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


def verify_agentmail(raw_body: bytes, headers: dict[str, str]) -> None:
    """Verify a Svix-signed AgentMail webhook. Raises on failure."""
    secret = os.environ.get(_SECRET_ENV)
    if not secret:
        raise RuntimeError(f"{_SECRET_ENV} not set")
    Webhook(secret).verify(raw_body, headers)


__all__ = ["verify_agentmail", "WebhookVerificationError"]
