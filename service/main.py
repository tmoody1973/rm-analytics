"""FastAPI service: AgentMail webhook -> Triton loader -> Neon.

Endpoints:
  GET  /health      - liveness probe
  POST /webhook/wms - AgentMail message.received events from triton-ingest@

Flow:
  1. Read raw body, verify Svix signature.
  2. Decode JSON, check event_type == "message.received".
  3. Extract subject, resolve to a loader via router.
  4. Find a data attachment (XLSX, CSV, or ZIP) and fetch its bytes.
  5. If ZIP, extract the inner CSV/XLSX. Write to a temp file with the right
     extension so the loader's CSV/XLSX dispatch reads it correctly.
  6. Call loader.load(path), post Slack on success/failure.
"""
from __future__ import annotations

import io
import logging
import tempfile
import zipfile
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

# AgentMail webhook subscriptions are account-wide, not inbox-scoped, so the
# service receives `message.received` events for every inbox on the account.
# We only want mail to triton-ingest@; everything else is ignored at this layer.
ALLOWED_INBOX = "triton-ingest@agentmail.to"

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
    inbox_id = message.get("inbox_id")
    if inbox_id != ALLOWED_INBOX:
        log.info("ignoring event for inbox=%r", inbox_id)
        return {"ignored": True, "reason": "wrong inbox", "inbox_id": inbox_id}

    subject = message.get("subject") or ""

    route = resolve(subject)
    if route is None:
        log.info("no route for subject=%r (known=%s)", subject, known_tags())
        return {"ignored": True, "reason": "no matching tag", "subject": subject}

    attachment = _pick_data_attachment(message.get("attachments") or [])
    if attachment is None:
        slack.post_failure(route.tag, "no csv/xlsx/zip attachment on message")
        raise HTTPException(status_code=422, detail="no data attachment")

    inbox_id = message.get("inbox_id")
    message_id = message.get("message_id")
    if not inbox_id or not message_id:
        slack.post_failure(route.tag, "missing inbox_id/message_id")
        raise HTTPException(status_code=422, detail="missing inbox/message id")

    try:
        blob = fetch_attachment_bytes(inbox_id, message_id, attachment["attachment_id"])
    except Exception as exc:
        log.exception("attachment fetch failed")
        slack.post_failure(route.tag, f"attachment fetch failed: {exc}")
        raise HTTPException(status_code=502, detail="attachment fetch failed") from exc

    filename = (attachment.get("filename") or "").lower()
    if filename.endswith(".zip"):
        try:
            blob, inner_name = _extract_data_from_zip(blob)
        except ValueError as exc:
            slack.post_failure(route.tag, f"zip extraction failed: {exc}")
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        suffix = "." + inner_name.rsplit(".", 1)[-1].lower()
    elif "." in filename:
        suffix = "." + filename.rsplit(".", 1)[-1]
    else:
        suffix = ".csv"  # safest default for Triton's scheduled exports

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
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


_DATA_SUFFIXES = (".csv", ".xlsx", ".zip")
_DATA_CTYPE_HINTS = ("spreadsheetml", "csv", "zip")


def _pick_data_attachment(attachments: list[dict[str, Any]]) -> dict[str, Any] | None:
    """First attachment that looks like a Triton export (CSV, XLSX, or ZIP).

    Triton's scheduled queries ship a CSV; bulk/historical exports are XLSX;
    Gmail's auto-forward wraps either inside a ZIP. All three are acceptable
    here — extraction happens upstream.
    """
    for att in attachments:
        filename = (att.get("filename") or "").lower()
        ctype = (att.get("content_type") or "").lower()
        if filename.endswith(_DATA_SUFFIXES):
            return att
        if any(hint in ctype for hint in _DATA_CTYPE_HINTS):
            return att
    return None


def _extract_data_from_zip(blob: bytes) -> tuple[bytes, str]:
    """Pull the first CSV or XLSX member out of a ZIP. Returns (bytes, name).

    Raises ValueError if the archive contains neither.
    """
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        members = [
            name
            for name in zf.namelist()
            if name.lower().endswith((".csv", ".xlsx"))
        ]
        if not members:
            raise ValueError(
                f"zip has no csv/xlsx member (members={zf.namelist()})"
            )
        inner = members[0]
        return zf.read(inner), inner
