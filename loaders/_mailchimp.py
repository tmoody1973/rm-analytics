"""Mailchimp Marketing API client + content parsing for newsletter analysis.

Only the campaign CONTENT endpoint is used here; performance metrics already
arrive via Coupler into email_esp.fact_campaign_sends. Auth is HTTP Basic with
any username and the API key as the password; the key's `-usNN` suffix selects
the data-center host.
"""
from __future__ import annotations

import re
import requests

_TIMEOUT_SEC = 30
_LINK_RE = re.compile(r'<a\b[^>]*\bhref="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def mailchimp_base_url(api_key: str) -> str:
    """Derive the data-center base URL from the API key's `-usNN` suffix."""
    if "-" not in api_key or not api_key.rsplit("-", 1)[-1]:
        raise ValueError("Mailchimp API key missing the `-usNN` data-center suffix")
    dc = api_key.rsplit("-", 1)[-1]
    return f"https://{dc}.api.mailchimp.com/3.0"


def parse_content(html: str | None, plain_text: str | None) -> dict:
    """Normalize a Mailchimp content payload into our storage shape."""
    text = (plain_text or "").strip()
    links: list[dict] = []
    if html:
        for url, raw_label in _LINK_RE.findall(html):
            label = _TAG_RE.sub("", raw_label).strip()
            links.append({"url": url, "label": label})
    return {
        "plain_text": text,
        "html": html if html else None,
        "links": links,
        "word_count": len(text.split()),
    }


def fetch_campaign_content(api_key: str, campaign_id: str, *, session=None) -> dict:
    """GET /campaigns/{id}/content -> raw JSON ({'plain_text','html', ...})."""
    http = session or requests
    url = f"{mailchimp_base_url(api_key)}/campaigns/{campaign_id}/content"
    resp = http.get(url, auth=("rm-analytics", api_key), timeout=_TIMEOUT_SEC)
    resp.raise_for_status()
    return resp.json()
