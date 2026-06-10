"""
End-to-end smoke test for the FastAPI webhook → Q1 loader → Neon chain.

We construct a Svix-signed AgentMail-shaped webhook with subject [WMS-Q1-HOURLY]
and an attachment metadata stub, then monkey-patch the AgentMail attachment
fetch to return the bytes of a 50-row slice of the real Q1 export.

The table already contains the full backfill (~60k rows). Idempotency is the
contract under test: re-upserting 50 already-present (station, date, hour)
keys must produce zero net-new rows. If the DB count changes, something is
wrong with the PK or the ON CONFLICT clause.

Run:  python tests/test_smoke_service_q1.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "loaders"))

os.environ.setdefault("AGENTMAIL_WEBHOOK_SECRET", "whsec_" + "A" * 40)
os.environ.setdefault("AGENTMAIL_API_KEY", "smoke-test-key")
os.environ.pop("SLACK_WEBHOOK_URL", None)
os.environ.pop("NOTIFY_EMAIL_TO", None)  # belt-and-suspenders: no test mail to a real inbox

from fastapi.testclient import TestClient  # noqa: E402
from svix.webhooks import Webhook  # noqa: E402

from service import agentmail_client, main  # noqa: E402
from _common import get_db_connection  # noqa: E402


SRC = os.path.join(ROOT, "exports", "Q1_hourly_2024-01-01_2026-05-16.xlsx")
TABLE = "wms.fact_hourly_listening"
N = 50


def _count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
        return cur.fetchone()[0]


def _signed_headers(body: bytes, msg_id: str) -> dict[str, str]:
    secret = os.environ["AGENTMAIL_WEBHOOK_SECRET"]
    now = datetime.now(tz=timezone.utc)
    signature = Webhook(secret).sign(msg_id, now, body.decode("utf-8"))
    return {
        "svix-id": msg_id,
        "svix-timestamp": str(int(now.timestamp())),
        "svix-signature": signature,
        "content-type": "application/json",
    }


def run() -> None:
    df = pd.read_excel(SRC, nrows=N)
    assert len(df) == N

    fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    df.to_excel(tmp_path, index=False)

    with open(tmp_path, "rb") as fh:
        xlsx_bytes = fh.read()

    # Patch the AgentMail attachment fetch so the service doesn't hit the network.
    def fake_fetch(inbox_id: str, message_id: str, attachment_id: str) -> bytes:
        return xlsx_bytes

    agentmail_client.fetch_attachment_bytes = fake_fetch
    main.fetch_attachment_bytes = fake_fetch  # already-bound import in main

    payload = {
        "type": "event",
        "event_type": "message.received",
        "event_id": "evt_smoke",
        "message": {
            "message_id": "msg_smoke",
            "thread_id": "thr_smoke",
            "inbox_id": "triton-ingest@agentmail.to",
            "from": "triton@noreply.tritondigital.com",
            "to": ["triton-ingest@agentmail.to"],
            "subject": "Triton WMS export [WMS-Q1-HOURLY] 2026-06-09",
            "text": "Q1 hourly export attached.",
            "attachments": [
                {
                    "attachment_id": "att_smoke",
                    "filename": "Q1_hourly_2026-06-09.xlsx",
                    "size": len(xlsx_bytes),
                    "content_type": (
                        "application/vnd.openxmlformats-"
                        "officedocument.spreadsheetml.sheet"
                    ),
                    "content_disposition": "attachment",
                }
            ],
            "timestamp": "2026-06-09T11:00:00Z",
        },
        "thread": {"thread_id": "thr_smoke"},
    }
    body = json.dumps(payload).encode("utf-8")
    headers = _signed_headers(body, "msg_smoke")

    try:
        conn = get_db_connection()
        try:
            before = _count(conn)
        finally:
            conn.close()
        assert before > 0, (
            f"{TABLE} is empty — this test asserts idempotent re-upsert against "
            "the live backfill; load the backfill first"
        )

        client = TestClient(main.app)

        health = client.get("/health")
        assert health.status_code == 200, f"health failed: {health.text}"
        assert "[WMS-Q1-HOURLY]" in health.json()["routes"]

        resp = client.post("/webhook/wms", content=body, headers=headers)
        assert resp.status_code == 200, f"webhook failed {resp.status_code}: {resp.text}"
        body_json = resp.json()
        assert body_json["ok"] is True
        assert body_json["tag"] == "[WMS-Q1-HOURLY]"
        stats = body_json["stats"]
        assert stats["rows_read"] == N
        assert stats["rows_upserted"] == N

        conn = get_db_connection()
        try:
            after = _count(conn)
        finally:
            conn.close()
        assert after == before, (
            f"row count changed: before={before} after={after} "
            "(50 rows from the real export should already exist — "
            "ON CONFLICT should be a no-op)"
        )

        # Also confirm bad signature is rejected.
        bad = client.post(
            "/webhook/wms",
            content=body,
            headers={**headers, "svix-signature": "v1,YmFkc2ln"},
        )
        assert bad.status_code == 401, f"expected 401 on bad sig, got {bad.status_code}"

        print(
            f"   rows_read={stats['rows_read']} rows_upserted={stats['rows_upserted']}"
            f" db_before={before} db_after={after} elapsed={stats['elapsed_sec']}s"
        )
        print("✅ service smoke test passed")
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        print("❌ service smoke test FAILED")
        traceback.print_exc()
        sys.exit(1)
