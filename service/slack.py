"""Slack webhook notifications for pipeline success / failure.

SLACK_WEBHOOK_URL is optional in dev — when unset, calls become no-ops so the
service still runs locally without a Slack integration.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests


log = logging.getLogger(__name__)

_WEBHOOK_ENV = "SLACK_WEBHOOK_URL"
_TIMEOUT_SEC = 10


def _post(text: str) -> None:
    url = os.environ.get(_WEBHOOK_ENV)
    if not url:
        log.info("SLACK (no webhook): %s", text)
        return
    try:
        resp = requests.post(url, json={"text": text}, timeout=_TIMEOUT_SEC)
        if resp.status_code >= 300:
            log.warning("Slack post failed %s: %s", resp.status_code, resp.text)
    except requests.RequestException as exc:
        log.warning("Slack post errored: %s", exc)


def post_success(tag: str, stats: dict[str, Any]) -> None:
    # Tolerant of any loader's stats shape — not every loader emits every key.
    upserted = stats.get("rows_upserted", "?")
    table = stats.get("table", "?")
    read = stats.get("rows_read", stats.get("periods", "?"))
    elapsed = stats.get("elapsed_sec", "?")
    text = (
        f":white_check_mark: *{tag}* upserted "
        f"{upserted} rows into `{table}` ({read} read, {elapsed}s)"
    )
    _post(text)


def post_failure(tag: str, err: str) -> None:
    _post(f":x: *{tag}* failed: `{err}`")
