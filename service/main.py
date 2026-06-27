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

import html
import importlib
import io
import json
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from svix.webhooks import WebhookVerificationError

from . import email, slack
from .agentmail_client import fetch_attachment_bytes
from .auth import verify_agentmail, verify_sheet_secret
from .internal_auth import require_internal_token
from .router import known_tags, resolve


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("rm-data-loader")

# AgentMail webhook subscriptions are account-wide, not inbox-scoped, so the
# service receives `message.received` events for every inbox on the account.
# We only want mail to triton-ingest@; everything else is ignored at this layer.
ALLOWED_INBOX = "triton-ingest@agentmail.to"

app = FastAPI(title="rm-data-loader", version="0.1.0")

# The RM Executive Dashboard web app (separate origin) reads /api/dashboard.
# Read-only aggregate data, GET only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

from . import ask_sql_api, catalog_api, chat_api, metric_api, newsletter_api

# Assistant tool endpoints (/api/metric, /api/metrics, /api/schema, /api/ask-sql,
# /api/newsletter-content) are called server-to-server by the Clerk-gated Vercel
# function, never by a browser. They expose the funraise (donor) schema via
# /api/ask-sql, so each is gated behind the shared INTERNAL_API_TOKEN secret.
# /api/dashboard (below) stays open — it is the browser's aggregate-only path.
_internal = [Depends(require_internal_token)]
app.include_router(metric_api.router, dependencies=_internal)
app.include_router(ask_sql_api.router, dependencies=_internal)
app.include_router(catalog_api.router, dependencies=_internal)
app.include_router(newsletter_api.router, dependencies=_internal)
app.include_router(chat_api.router, dependencies=_internal)


@app.get("/api/dashboard")
def api_dashboard() -> dict:
    """All data the RM Executive Dashboard app needs, as one JSON payload."""
    from . import dashboard_api
    return dashboard_api.dashboard_data()


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
        _notify_failure(route.tag, "no csv/xlsx/zip attachment on message")
        raise HTTPException(status_code=422, detail="no data attachment")

    inbox_id = message.get("inbox_id")
    message_id = message.get("message_id")
    if not inbox_id or not message_id:
        _notify_failure(route.tag, "missing inbox_id/message_id")
        raise HTTPException(status_code=422, detail="missing inbox/message id")

    try:
        blob = fetch_attachment_bytes(inbox_id, message_id, attachment["attachment_id"])
    except Exception as exc:
        log.exception("attachment fetch failed")
        _notify_failure(route.tag, f"attachment fetch failed: {exc}")
        raise HTTPException(status_code=502, detail="attachment fetch failed") from exc

    filename = (attachment.get("filename") or "").lower()
    if filename.endswith(".zip"):
        try:
            blob, inner_name = _extract_data_from_zip(blob)
        except ValueError as exc:
            _notify_failure(route.tag, f"zip extraction failed: {exc}")
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
        _notify_failure(route.tag, f"loader failed: {exc}")
        raise HTTPException(status_code=500, detail="loader failed") from exc
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    log.info("loaded %s: %s", route.tag, stats)
    _notify_success(route.tag, stats)
    return {"ok": True, "tag": route.tag, "stats": stats}


# Map a sheet "dataset" to its loader module. Unknown datasets fall back to the
# generic tabular loader. Loaders resolve because the router import (above) put the
# loaders/ dir on sys.path.
_SHEET_LOADERS = {"finance_kpi": "load_finance_sheet"}


@app.post("/webhook/sheet")
async def webhook_sheet(request: Request) -> dict[str, Any]:
    """Google Sheets 'Sync to Neon' push (finance KPIs today; more later)."""
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        verify_sheet_secret(headers)
    except WebhookVerificationError as exc:
        log.warning("sheet secret verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="invalid secret") from exc

    payload = await request.json()
    dataset = payload.get("dataset") or "?"
    tag = f"[SHEET-{dataset}]"

    loader = importlib.import_module(_SHEET_LOADERS.get(dataset, "load_sheet_sync"))
    try:
        stats = loader.load(payload)
    except Exception as exc:
        log.exception("sheet loader failed for dataset=%s", dataset)
        _notify_failure(tag, f"loader failed: {exc}")
        raise HTTPException(status_code=500, detail="loader failed") from exc

    log.info("loaded %s: %s", tag, stats)
    _notify_success(tag, stats)
    return {"ok": True, "dataset": dataset, "stats": stats}


@app.post("/webhook/funraise")
async def webhook_funraise(request: Request) -> Any:
    """Funraise transaction webhook -> funraise.fact_transactions.

    On the first (subscription) call Funraise sends an `x-hook-secret` header with
    an empty body; we echo it back to confirm the subscription. Real events carry a
    JSON body. TODO: verify the signature with FUNRAISE_WEBHOOK_SECRET once confirmed.
    """
    headers = {k.lower(): v for k, v in request.headers.items()}
    body = await request.body()

    hook_secret = headers.get("x-hook-secret")
    if hook_secret and not body:
        return Response(headers={"x-hook-secret": hook_secret})

    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid json") from exc

    loader = importlib.import_module("load_funraise_webhook")
    try:
        stats = loader.load(payload)
    except Exception as exc:
        log.exception("funraise loader failed")
        _notify_failure("[FUNRAISE]", f"loader failed: {exc}")
        raise HTTPException(status_code=500, detail="loader failed") from exc

    log.info("loaded [FUNRAISE]: %s", stats)
    _notify_success("[FUNRAISE]", stats)
    return {"ok": True, "stats": stats}


_NIELSEN_FORM = """<!doctype html>
<html><head><meta charset="utf-8"><title>Nielsen Vital Signs Upload</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:3rem auto;padding:0 1rem;color:#1a1a1a}
 h1{font-size:1.4rem}
 .card{border:1px solid #e2e2e2;border-radius:12px;padding:1.5rem;box-shadow:0 1px 3px rgba(0,0,0,.05)}
 input[type=file]{margin:1rem 0;display:block}
 button{background:#5b21b6;color:#fff;border:0;border-radius:8px;padding:.7rem 1.4rem;font-size:1rem;cursor:pointer}
 .hint{color:#555;font-size:.92rem;line-height:1.55} .ok{color:#15803d;font-weight:600} .err{color:#b91c1c;font-weight:600}
</style></head><body>
<h1>&#128251; Nielsen Vital Signs &mdash; Upload</h1>
<div class="card">
<p class="hint">Export the <b>Vital Signs Trend</b> report from Nielsen (any station, demo, or daypart)
as <b>CSV</b>, then upload it here. The file describes itself &mdash; you don't need to pick anything.
Re-uploading is safe: new months are added, existing months are refreshed, nothing is duplicated.</p>
<form method="post" enctype="multipart/form-data" action="/upload/nielsen">
<input type="file" name="file" accept=".csv" required>
<button type="submit">Upload to warehouse</button>
</form>
</div>
__RESULT__
</body></html>"""


def _nielsen_page(result_html: str = "") -> str:
    return _NIELSEN_FORM.replace("__RESULT__", result_html)


@app.get("/upload/nielsen", response_class=HTMLResponse)
def nielsen_form() -> str:
    return _nielsen_page()


@app.post("/upload/nielsen", response_class=HTMLResponse)
async def nielsen_upload(file: UploadFile = File(...)) -> str:
    """Browser upload of a Nielsen Vital Signs CSV -> nielsen.fact_vital_signs."""
    data = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as fh:
        fh.write(data)
        tmp = Path(fh.name)

    loader = importlib.import_module("load_nielsen")
    try:
        stats = loader.load(str(tmp))
    except Exception as exc:
        log.exception("nielsen upload failed")
        _notify_failure("[NIELSEN]", f"upload failed: {exc}")
        return _nielsen_page(f'<p class="err">&#10060; Upload failed: {html.escape(str(exc))}</p>')
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass

    log.info("loaded [NIELSEN]: %s", stats)
    _notify_success("[NIELSEN]", stats)
    msg = (f'<p class="ok">&#9989; Loaded {html.escape(stats["station"])} &middot; '
           f'{html.escape(stats["demo"])} &middot; {html.escape(stats["daypart"])} '
           f'&mdash; {stats["rows_upserted"]} rows across {stats["periods"]} periods.</p>')
    return _nielsen_page(msg)


def _notify_success(tag: str, stats: dict[str, Any]) -> None:
    """Fan-out success to every configured channel. Each channel is a no-op
    if its env var isn't set, so dev/local stays silent."""
    slack.post_success(tag, stats)
    email.post_success(tag, stats)


def _notify_failure(tag: str, err: str) -> None:
    """Fan-out failure to every configured channel."""
    slack.post_failure(tag, err)
    email.post_failure(tag, err)


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
