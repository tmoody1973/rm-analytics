import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "loaders"))

import pytest
import load_socialfetch as loader

ACCOUNT = {"account_id": "ig:hyfinmke", "platform": "instagram", "handle": "hyfinmke"}


def _patch_db(monkeypatch, captured, existing_enriched=None):
    """Stub bulk_upsert + the 'which post_ids already enriched' query."""
    def fake_bulk_upsert(conn, table, columns, rows, conflict_columns, update_columns, batch_size=5000):
        captured.setdefault(table, []).append(rows)
        return len(rows)
    monkeypatch.setattr(loader, "bulk_upsert", fake_bulk_upsert)
    monkeypatch.setattr(loader, "_already_enriched",
                        lambda conn, post_ids: set(existing_enriched or []))


def test_load_skips_when_account_not_found(monkeypatch):
    monkeypatch.setattr(loader, "fetch_account", lambda account, *, api_key, session=None: None)
    captured = {}
    _patch_db(monkeypatch, captured)
    stats = loader.load(ACCOUNT, api_key="k", client=object(), conn=object())
    assert stats["skipped"] is True
    assert stats["posts_upserted"] == 0
    assert captured == {}                       # nothing written for a skipped account


def test_load_upserts_snapshot_posts_and_enriches_new(monkeypatch):
    raw = {"lookupStatus": "ok", "data": {
        "profile": {"followerCount": 100},
        "posts": [
            {"id": "p1", "type": "reel", "caption": "New track from Klassik", "likeCount": 10, "commentCount": 5},
            {"id": "p2", "type": "image", "caption": "", "likeCount": 2},
        ],
    }}
    monkeypatch.setattr(loader, "fetch_account", lambda account, *, api_key, session=None: raw)

    enrich_calls = []
    def fake_enrich(client, caption, *, model):
        enrich_calls.append(caption)
        return {"content_theme": "local_artist_feature", "format": "reel",
                "primary_topic": "local_music", "hook_style": "announcement",
                "has_cta": False, "featured_artists": ["Klassik"]}
    monkeypatch.setattr(loader, "enrich_post", fake_enrich)

    captured = {}
    _patch_db(monkeypatch, captured, existing_enriched=[])
    stats = loader.load(ACCOUNT, api_key="k", client=object(), conn=object())

    assert stats["snapshots_upserted"] == 1
    assert stats["posts_upserted"] == 2
    # only p1 has a caption -> only one LLM call
    assert enrich_calls == ["New track from Klassik"]
    assert stats["enriched"] == 1
    assert "social_intel.fact_account_snapshots" in captured
    assert "social_intel.fact_posts" in captured
    assert "social_intel.fact_post_enrichment" in captured


def test_load_skips_already_enriched_posts(monkeypatch):
    raw = {"lookupStatus": "ok", "data": {
        "profile": {"followerCount": 100},
        "posts": [{"id": "p1", "type": "reel", "caption": "hello", "likeCount": 1}],
    }}
    monkeypatch.setattr(loader, "fetch_account", lambda account, *, api_key, session=None: raw)
    enrich_calls = []
    monkeypatch.setattr(loader, "enrich_post",
                        lambda client, caption, *, model: enrich_calls.append(caption) or {})
    captured = {}
    _patch_db(monkeypatch, captured, existing_enriched=["p1"])   # already tagged
    stats = loader.load(ACCOUNT, api_key="k", client=object(), conn=object())
    assert enrich_calls == []                  # no re-tagging -> flat weekly cost
    assert stats["enriched"] == 0
