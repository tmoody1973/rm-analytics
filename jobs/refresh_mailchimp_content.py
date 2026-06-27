"""Daily sweep: fetch + enrich any sent campaign missing a content row.

Piggybacks the Coupler cadence — newsletter content's real-time-ness buys
nothing because the open/click metrics it correlates against accrue over days.
This sweep is also the reconciliation safety net if a webhook is added later.

Fly scheduled machine `mailchimp-content-nightly`. CLI:
  python jobs/refresh_mailchimp_content.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "loaders"))
sys.path.insert(0, ROOT)
from load_mailchimp_content import load  # noqa: E402
from service.slack import post_success, post_failure  # noqa: E402

TAG = "[ESP-CONTENT]"


def run() -> dict:
    try:
        stats = load(None)            # sweep mode: campaigns missing content
        stats["tag"] = TAG
        post_success(TAG, stats)
        return stats
    except Exception as exc:          # noqa: BLE001 — report then re-raise
        post_failure(TAG, str(exc))
        raise


if __name__ == "__main__":
    print(run())
