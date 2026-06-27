"""Tests for the newsletter-content retrieval endpoint (Phase B / MOO-177).

The DB layer is mocked — these assert the shaping (capping/null/iso) and the
route's 404-vs-200 behavior, with no real rm_readonly connection required.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException

from service import newsletter_api


def test_shape_row_caps_body_and_flags_truncation():
    long_body = "x " * 5000  # ~10000 chars, over the cap
    row = {
        "campaign_id": "c1", "plain_text": long_body, "word_count": 5000,
        "content_type": "newsletter", "primary_theme": "events",
        "topics": ["events"], "featured_artists": ["Klassik"],
        "subject_line": "Hi", "send_time": None,
    }
    out = newsletter_api.shape_row(row)
    assert len(out["plain_text"]) == newsletter_api.MAX_PLAIN_TEXT_CHARS
    assert out["truncated"] is True
    assert out["topics"] == ["events"]
    assert out["featured_artists"] == ["Klassik"]
    assert out["campaign_id"] == "c1"


def test_shape_row_nulls_become_empty():
    row = {
        "campaign_id": "c2", "plain_text": None, "word_count": 0,
        "content_type": None, "primary_theme": None, "topics": None,
        "featured_artists": None, "subject_line": None, "send_time": None,
    }
    out = newsletter_api.shape_row(row)
    assert out["plain_text"] == ""
    assert out["truncated"] is False
    assert out["topics"] == []
    assert out["featured_artists"] == []


def test_shape_row_iso_formats_send_time():
    row = {
        "campaign_id": "c3", "plain_text": "hi", "word_count": 1,
        "content_type": None, "primary_theme": None, "topics": [],
        "featured_artists": [], "subject_line": None,
        "send_time": datetime(2026, 6, 1, 12, 0, 0),
    }
    out = newsletter_api.shape_row(row)
    assert out["send_time"] == "2026-06-01T12:00:00"


def test_route_raises_404_when_no_content(monkeypatch):
    monkeypatch.setattr(newsletter_api, "fetch_newsletter_content", lambda cid: None)
    with pytest.raises(HTTPException) as ei:
        newsletter_api.get_newsletter_content("does-not-exist")
    assert ei.value.status_code == 404


def test_route_returns_payload_on_hit(monkeypatch):
    payload = {
        "campaign_id": "c9", "subject_line": "S", "send_time": None,
        "word_count": 3, "content_type": "newsletter", "primary_theme": "events",
        "topics": ["events"], "featured_artists": [], "plain_text": "body",
        "truncated": False,
    }
    monkeypatch.setattr(newsletter_api, "fetch_newsletter_content", lambda cid: payload)
    assert newsletter_api.get_newsletter_content("c9") == payload
