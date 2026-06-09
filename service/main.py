"""FastAPI service: AgentMail webhook -> Triton loader -> Neon.

Endpoints:
  GET  /health      - liveness probe
  POST /webhook/wms - AgentMail message.received events from triton-ingest@

Flow:
  1. Read raw body, verify Svix signature.
  2. Decode JSON, check event_type == "message.received".
  3. Extract subject, resolve to a loader via router.
  4. Find the first XLSX attachment, fetch its bytes from AgentMail API.
  5. Write to a temp file, call loader.load(path), post Slack on success/failure.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from svix.webhooks import WebhookVerificationError

from . import slack
from .agentmail_client import fetch_attachment_bytes
from .auth import verify_agentmail
from .router import known_tags, resolve


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("rm-data-loader")

app = FastAPI(title="rm-data-loader", version="0.1.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "routes": known_tags()}


@app.post("/webhook/wms")
async def webhook_wms(request: Request) -> dict[str, Any]:
    raw_body = await request.body()

    try:
        verify_agentmail(raw_body, dict(request.headers))
    except WebhookVerificationError as exc:
        log.warning("signature verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="invalid signature") from exc

    payload = await request.json()
    event_type = payload.get("event_type")
    if event_type != "message.received":
        log.info("ignoring event_type=%s", event_type)
        return {"ignored": True, "event_type": event_type}

    message = payload.get("message") or {}
    subject = message.get("subject") or ""

    route = resolve(subject)
    if route is None:
        log.info("no route for subject=%r (known=%s)", subject, known_tags())
        return {"ignored": True, "reason": "no matching tag", "subject": subject}

    xlsx = _pick_xlsx_attachment(message.get("attachments") or [])
    if xlsx is None:
        slack.post_failure(route.tag, "no XLSX attachment on message")
        raise HTTPException(status_code=422, detail="no xlsx attachment")

    inbox_id = message.get("inbox_id")
    message_id = message.get("message_id")
    if not inbox_id or not message_id:
        slack.post_failure(route.tag, "missing inbox_id/message_id")
        raise HTTPException(status_code=422, detail="missing inbox/message id")

    try:
        blob = fetch_attachment_bytes(inbox_id, message_id, xlsx["attachment_id"])
    except Exception as exc:
        log.exception("attachment fetch failed")
        slack.post_failure(route.tag, f"attachment fetch failed: {exc}")
        raise HTTPException(status_code=502, detail="attachment fetch failed") from exc

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as fh:
        fh.write(blob)
        tmp_path = Path(fh.name)

    try:
        stats = route.loader(str(tmp_path))
    except Exception as exc:
        log.exception("loader failed for %s", route.tag)
        slack.post_failure(route.tag, f"loader failed: {exc}")
        raise HTTPException(status_code=500, detail="loader failed") from exc
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    log.info("loaded %s: %s", route.tag, stats)
    slack.post_success(route.tag, stats)
    return {"ok": True, "tag": route.tag, "stats": stats}


def _pick_xlsx_attachment(attachments: list[dict[str, Any]]) -> dict[str, Any] | None:
    for att in attachments:
        filename = (att.get("filename") or "").lower()
        ctype = (att.get("content_type") or "").lower()
        if filename.endswith(".xlsx") or "spreadsheetml" in ctype:
            return att
    return None
