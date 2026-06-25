"""Email notifications via AgentMail send API.

Mirrors service/slack.py: success/failure helpers, no-op when the recipient
env var is unset (so local/dev runs stay silent without spamming a real
inbox).

Two intentional design choices baked in:

1. Sender inbox is `tarik@agentmail.to`, NOT `triton-ingest@agentmail.to`.
   Sending from triton-ingest would risk producing a self-triggered
   message.received event on the same inbox the webhook listens to. Sending
   from `tarik@` keeps the inbox guard's "wrong inbox" filter applicable as
   a safety net even if AgentMail emits a sent-side event we didn't expect.
2. Subject and body avoid the literal substring `[WMS-`. The user has a
   Gmail rule that auto-forwards anything from `noreply@tritondigital.com`
   containing `[WMS-` to triton-ingest@agentmail.to. If our success email
   used the bracketed tag it could ping-pong back through that rule. We
   use the inner tag form (`Q1-HOURLY`, no brackets) which is human-readable
   and bypass-safe.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests


log = logging.getLogger(__name__)

_TO_ENV = "NOTIFY_EMAIL_TO"
_API_KEY_ENV = "AGENTMAIL_API_KEY"
_FROM_INBOX = "tarik@agentmail.to"
_API_BASE = "https://api.agentmail.to/v0"
_TIMEOUT_SEC = 10


def _strip_brackets(tag: str) -> str:
    """`[WMS-Q1-HOURLY]` -> `Q1-HOURLY`. Idempotent on already-stripped tags."""
    body = tag.strip()
    if body.startswith("[") and body.endswith("]"):
        body = body[1:-1]
    return body.removeprefix("WMS-")


def _send(subject: str, text: str) -> None:
    to = os.environ.get(_TO_ENV)
    if not to:
        log.info("EMAIL (no recipient set): %s", subject)
        return
    api_key = os.environ.get(_API_KEY_ENV)
    if not api_key:
        log.warning("AGENTMAIL_API_KEY not set; can't send notification")
        return

    url = f"{_API_BASE}/inboxes/{_FROM_INBOX}/messages/send"
    body = {"to": to, "subject": subject, "text": text}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=_TIMEOUT_SEC)
        if resp.status_code >= 300:
            log.warning("Email send failed %s: %s", resp.status_code, resp.text)
    except requests.RequestException as exc:
        log.warning("Email send errored: %s", exc)


def post_success(tag: str, stats: dict[str, Any]) -> None:
    short = _strip_brackets(tag)
    # Tolerant of any loader's stats shape — not every loader emits every key.
    upserted = stats.get("rows_upserted", "?")
    table = stats.get("table", "?")
    read = stats.get("rows_read", stats.get("periods", "?"))
    elapsed = stats.get("elapsed_sec", "?")
    subject = f"OK {short}: {upserted} rows -> {table}"
    text = (
        "Report processed into Neon.\n\n"
        f"Tag:           {short}\n"
        f"Query:         {stats.get('query', '?')}\n"
        f"Target table:  {table}\n"
        f"Rows read:     {read}\n"
        f"Rows upserted: {upserted}\n"
        f"Elapsed:       {elapsed}s\n"
    )
    _send(subject, text)


def post_failure(tag: str, err: str) -> None:
    short = _strip_brackets(tag)
    subject = f"FAIL {short}: {err[:80]}"
    text = (
        "Triton report ingestion FAILED.\n\n"
        f"Tag:   {short}\n"
        f"Error: {err}\n\n"
        "Inspect logs:\n"
        "  flyctl logs --app rm-data-loader\n"
    )
    _send(subject, text)
