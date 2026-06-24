"""
Funraise nightly reconciliation pull (supporters + subscriptions + late edits).

Even with the real-time transaction webhook, a nightly API pull of the last N days
catches anything the webhook missed (network blips, retries) and refreshes the
slow-changing dim_supporters / fact_subscriptions / dim_campaigns, which have no
webhook of their own.

CLI:   python loaders/load_funraise_api_pull.py [days_back]
Cron:  jobs/nightly_funraise_pull.py calls load().

TODO: wire the real Funraise REST endpoints + FUNRAISE_API_KEY auth and finalize the
field maps against a real API response. Until then load() raises a clear error.
"""
from __future__ import annotations

import os
import sys
import time

import requests

API_BASE = os.environ.get("FUNRAISE_API_BASE", "https://api.funraise.io")  # TODO confirm
_TIMEOUT_SEC = 30


def _api_key() -> str:
    key = os.environ.get("FUNRAISE_API_KEY")
    if not key:
        raise RuntimeError("FUNRAISE_API_KEY not set")
    return key


def _session() -> requests.Session:
    session = requests.Session()
    # TODO: confirm the auth scheme (Bearer token vs custom header).
    session.headers.update({"Authorization": f"Bearer {_api_key()}"})
    return session


def fetch_supporters(session: requests.Session) -> list[dict]:
    """TODO: confirm the supporters endpoint + pagination, return raw records."""
    raise NotImplementedError("Funraise supporters endpoint not confirmed yet")


def fetch_subscriptions(session: requests.Session) -> list[dict]:
    """TODO: confirm the subscriptions endpoint + pagination, return raw records."""
    raise NotImplementedError("Funraise subscriptions endpoint not confirmed yet")


def load(days_back: int = 7) -> dict:
    """Pull + upsert supporters/subscriptions for the last `days_back` days.

    Scaffolded; raises until the Funraise API key + endpoints are confirmed.
    """
    _ = time.time()
    raise NotImplementedError(
        "Funraise API pull is scaffolded but pending creds + endpoint confirmation"
    )


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    print(load(days))
