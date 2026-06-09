"""Fetch attachment bytes from AgentMail.

The webhook payload only carries attachment metadata. To get the file we:
  1. GET /v0/inboxes/{inbox_id}/messages/{message_id}/attachments/{attachment_id}
     -> JSON with `download_url` (presigned, time-limited).
  2. GET the download_url -> raw bytes.

API key lives in AGENTMAIL_API_KEY (Bearer auth).
"""
from __future__ import annotations

import os

import requests


_API_BASE = "https://api.agentmail.to/v0"
_API_KEY_ENV = "AGENTMAIL_API_KEY"
_TIMEOUT_SEC = 30


def _bearer_headers() -> dict[str, str]:
    key = os.environ.get(_API_KEY_ENV)
    if not key:
        raise RuntimeError(f"{_API_KEY_ENV} not set")
    return {"Authorization": f"Bearer {key}"}


def fetch_attachment_bytes(
    inbox_id: str, message_id: str, attachment_id: str
) -> bytes:
    """Return the raw attachment bytes. Raises HTTPError on non-2xx."""
    meta_url = (
        f"{_API_BASE}/inboxes/{inbox_id}/messages/{message_id}"
        f"/attachments/{attachment_id}"
    )
    meta = requests.get(meta_url, headers=_bearer_headers(), timeout=_TIMEOUT_SEC)
    meta.raise_for_status()
    download_url = meta.json()["download_url"]

    blob = requests.get(download_url, timeout=_TIMEOUT_SEC)
    blob.raise_for_status()
    return blob.content
