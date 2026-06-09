"""
One-shot: register the AgentMail webhook for triton-ingest@ and print the
signing secret so we can hand it to Fly.

Idempotent via `client_id`. Re-running won't create duplicates — it returns
the existing webhook + secret. Safe to invoke after every URL change.

Usage:
    python jobs/register_agentmail_webhook.py \
        --url https://rm-data-loader.fly.dev/webhook/wms \
        --inbox triton-ingest@agentmail.to

Then copy the printed `whsec_...` value and:
    fly secrets set AGENTMAIL_WEBHOOK_SECRET=whsec_... --app rm-data-loader
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


_API_BASE = "https://api.agentmail.to/v0"
_ENV_PATH = Path.home() / ".radio-milwaukee" / ".env"
_CLIENT_ID = "rm-data-loader-wms"


def _headers() -> dict[str, str]:
    if not os.environ.get("AGENTMAIL_API_KEY") and _ENV_PATH.exists():
        load_dotenv(_ENV_PATH)
    key = os.environ.get("AGENTMAIL_API_KEY")
    if not key:
        sys.exit(f"AGENTMAIL_API_KEY not set (looked in env and {_ENV_PATH})")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _create_or_get(url: str, inbox: str) -> dict:
    body = {
        "url": url,
        "event_types": ["message.received"],
        "client_id": _CLIENT_ID,
        "inboxes": [inbox],
    }
    resp = requests.post(
        f"{_API_BASE}/webhooks", headers=_headers(), data=json.dumps(body), timeout=30
    )
    if resp.status_code >= 400:
        sys.exit(f"create webhook failed ({resp.status_code}): {resp.text}")
    return resp.json()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--url",
        default="https://rm-data-loader.fly.dev/webhook/wms",
        help="public webhook URL Fly will receive POSTs at",
    )
    ap.add_argument(
        "--inbox",
        default="triton-ingest@agentmail.to",
        help="inbox to scope events to",
    )
    args = ap.parse_args()

    webhook = _create_or_get(args.url, args.inbox)

    webhook_id = webhook.get("webhook_id") or webhook.get("id")
    secret = webhook.get("secret")

    print("webhook_id:", webhook_id)
    print("url:       ", webhook.get("url"))
    print("events:    ", webhook.get("event_types"))
    print("secret:    ", secret)
    print()
    print("Next:")
    print(
        f"  flyctl secrets set AGENTMAIL_WEBHOOK_SECRET={secret} "
        "--app rm-data-loader"
    )


if __name__ == "__main__":
    main()
