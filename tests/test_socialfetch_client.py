import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "loaders"))

import pytest
import _socialfetch as sf

ACCOUNT = {"account_id": "ig:hyfinmke", "platform": "instagram", "handle": "hyfinmke"}


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def get(self, url, *, headers, params=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "params": params})
        return self._resp


def test_fetch_sends_api_key_header():
    sess = _Session(_Resp(200, {"lookupStatus": "ok", "data": {"profile": {}, "posts": []}}))
    sf.fetch_account(ACCOUNT, api_key="sfk_test", session=sess)
    assert sess.calls[0]["headers"]["x-api-key"] == "sfk_test"


def test_fetch_returns_none_on_not_found():
    sess = _Session(_Resp(200, {"lookupStatus": "not_found"}))
    assert sf.fetch_account(ACCOUNT, api_key="k", session=sess) is None


def test_fetch_returns_none_on_private():
    sess = _Session(_Resp(200, {"lookupStatus": "private"}))
    assert sf.fetch_account(ACCOUNT, api_key="k", session=sess) is None


def test_fetch_raises_on_402_credits():
    sess = _Session(_Resp(402, {"error": "insufficient credits"}))
    with pytest.raises(sf.SocialfetchCreditError):
        sf.fetch_account(ACCOUNT, api_key="k", session=sess)


def test_normalize_real_fixture_shapes():
    raw = json.loads((Path(__file__).parent / "fixtures" / "socialfetch_sample.json").read_text())
    out = sf.normalize(ACCOUNT, raw)
    # snapshot tuple matches column count
    assert len(out["snapshot"]) == len(sf._SNAPSHOT_COLUMNS)
    # every post tuple matches column count
    for row in out["posts"]:
        assert len(row) == len(sf._POST_COLUMNS)
    # captions map keys are post_ids present in posts
    post_ids = {r[1] for r in out["posts"]}  # (account_id, post_id, ...)
    assert set(out["captions"]).issubset(post_ids)


def test_engagement_rate_uses_followers_at_fetch():
    raw = {
        "lookupStatus": "ok",
        "data": {
            "profile": {"followerCount": 100},
            "posts": [{"id": "p1", "likeCount": 8, "commentCount": 2, "shareCount": 0, "saveCount": 0}],
        },
    }
    out = sf.normalize(ACCOUNT, raw)
    er_index = sf._POST_COLUMNS.index("engagement_rate")
    assert out["posts"][0][er_index] == pytest.approx(0.10)  # (8+2)/100


def test_normalize_zero_followers_yields_null_rate():
    raw = {
        "lookupStatus": "ok",
        "data": {
            "profile": {"followerCount": 0},
            "posts": [{"id": "p1", "likeCount": 5}],
        },
    }
    out = sf.normalize(ACCOUNT, raw)
    er_index = sf._POST_COLUMNS.index("engagement_rate")
    assert out["posts"][0][er_index] is None  # no divide-by-zero


# --- Additional fixture-locking tests (confirm real API shape) ---


def test_normalize_real_fixture_values():
    """Lock confirmed field mapping against the captured radiomilwaukee fixture."""
    raw = json.loads((Path(__file__).parent / "fixtures" / "socialfetch_sample.json").read_text())
    out = sf.normalize(ACCOUNT, raw)

    # Follower count from data.metrics.followers
    snap = out["snapshot"]
    follower_idx = sf._SNAPSHOT_COLUMNS.index("follower_count")
    assert snap[follower_idx] == 41223

    # All 12 recent posts are returned
    assert len(out["posts"]) == 12

    # Every post has a non-null post_id
    post_id_idx = sf._POST_COLUMNS.index("post_id")
    assert all(row[post_id_idx] for row in out["posts"])

    # At least one post has a non-null engagement_rate
    er_idx = sf._POST_COLUMNS.index("engagement_rate")
    rates = [row[er_idx] for row in out["posts"]]
    assert any(r is not None for r in rates)

    # Spot-check first post: id=3926794101937272633, likes=42, comments=2
    first = out["posts"][0]
    likes_idx = sf._POST_COLUMNS.index("likes")
    comments_idx = sf._POST_COLUMNS.index("comments_count")
    assert first[likes_idx] == 42
    assert first[comments_idx] == 2
    expected_rate = round((42 + 2) / 41223, 6)
    assert first[er_idx] == pytest.approx(expected_rate)

    pub_idx = sf._POST_COLUMNS.index("published_at")
    assert isinstance(out["posts"][0][pub_idx], datetime)

    type_idx = sf._POST_COLUMNS.index("post_type")
    assert out["posts"][0][type_idx] == "carousel"


def test_fetch_returns_none_on_private_nested():
    """lookupStatus nested under data (real API shape) still triggers None return."""
    sess = _Session(_Resp(200, {"data": {"lookupStatus": "private"}}))
    assert sf.fetch_account(ACCOUNT, api_key="k", session=sess) is None


def test_fetch_returns_none_on_not_found_nested():
    """lookupStatus nested under data with not_found also returns None."""
    sess = _Session(_Resp(200, {"data": {"lookupStatus": "not_found"}}))
    assert sf.fetch_account(ACCOUNT, api_key="k", session=sess) is None
