"""socialfetch.dev REST client + cross-platform normalizer.

REST base https://api.socialfetch.dev, header `x-api-key: sfk_...` on every /v1/**.
Routes + field names are confirmed against the captured fixture
tests/fixtures/socialfetch_sample.json (radiomilwaukee Instagram profile, real API call).

Real shape (confirmed):
  {"data": {"lookupStatus": "found", "profile": {...}, "metrics": {...}, "recentPosts": [...]}, "meta": {...}}
  - data.lookupStatus: "found" | "not_found" | "private"
  - data.metrics: {"followers": int, "following": int, "posts": int}  ← counts live HERE
  - data.profile: platform, handle, displayName, verified (bool), privateAccount, etc.
                  profile does NOT contain follower/following/post counts.
  - data.recentPosts: list of posts. Per post: id, shortcode, mediaType ("sidecar"/"image"/"video"),
                      caption, takenAt (Unix epoch int), commentCount, likeCount,
                      videoViewCount (optional), displayUrl, thumbnailUrl, dimensions.
                      No shareCount/saveCount in the IG shape; those default to 0.
  - meta: {requestId, creditsCharged, version}  (ignored)

A 200 response can still be lookupStatus not_found/private → return None, skip.
HTTP 402 = out of credits → raise SocialfetchCreditError so the job aborts + alerts.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))
from _common import coerce_int, coerce_str  # noqa: E402

import requests
from urllib.parse import quote

_BASE = "https://api.socialfetch.dev"
_TIMEOUT_SEC = 30

# Route template — confirmed against the live /openapi.json (2026-06-28).
# Handle goes in the PATH (not a query param); this profile endpoint's payload
# already includes data.recentPosts, so one call per account covers profile+posts.
_PROFILE_ROUTE = "/v1/{platform}/profiles/{handle}"

# Raw socialfetch post_type/media_type -> our closed vocab.
POST_TYPE_MAP: dict[str, str] = {
    "reel": "reel",
    "clip": "reel",
    "carousel": "carousel",
    "album": "carousel",
    "sidecar": "carousel",
    "image": "image",
    "photo": "image",
    "picture": "image",
    "video": "video",
    "short": "short",
    "shorts": "short",
    "text": "text",
    "status": "text",
    "tweet": "text",
}

_SNAPSHOT_COLUMNS: list[str] = [
    "account_id",
    "snapshot_date",
    "follower_count",
    "following_count",
    "post_count",
    "verified",
]

_POST_COLUMNS: list[str] = [
    "account_id",
    "post_id",
    "platform",
    "published_at",
    "post_type",
    "caption",
    "transcript",
    "likes",
    "comments_count",
    "shares",
    "views",
    "saves",
    "engagement_rate",
    "permalink",
]


class SocialfetchCreditError(RuntimeError):
    """HTTP 402 — socialfetch credits exhausted; abort the run."""


def _first(d: dict, *keys: str, default: Any = None) -> Any:
    """Return the first present, non-None value among candidate keys."""
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return default


def _to_dt(v: Any) -> datetime | None:
    """Convert a Unix epoch int, numeric string, or ISO-8601 string to a UTC datetime.

    Returns None on None, empty, or unparseable input.
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            return None
    s = str(v).strip()
    if not s:
        return None
    if s.isdigit():
        try:
            return datetime.fromtimestamp(int(s), tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_account(account: dict, *, api_key: str, session=None) -> dict | None:
    """Fetch one account's profile (+ recent posts) from socialfetch.

    Returns the full raw payload dict on success, or None when the account is
    not_found or private (skip gracefully). Raises SocialfetchCreditError on HTTP 402.

    The `lookupStatus` field is read tolerantly: either at `data.lookupStatus`
    (real API shape) or at top-level `lookupStatus` (unit test mocks). Both work.
    """
    http = session or requests
    headers = {"x-api-key": api_key}
    url = _BASE + _PROFILE_ROUTE.format(
        platform=account["platform"],
        handle=quote(str(account["handle"]), safe=""),
    )
    resp = http.get(url, headers=headers, timeout=_TIMEOUT_SEC)
    if resp.status_code == 402:
        raise SocialfetchCreditError(f"HTTP 402 — socialfetch credits exhausted for {account['account_id']!r}")
    if resp.status_code != 200:
        resp.raise_for_status()
    payload = resp.json()
    # Tolerant lookupStatus read: check data.lookupStatus first (real API), then top-level (tests).
    status = (
        (payload.get("data") or {}).get("lookupStatus")
        or payload.get("lookupStatus")
        or ""
    ).lower()
    if status in ("not_found", "private"):
        return None
    return payload


def _count(metrics: dict, profile: dict, *keys: str) -> int:
    """Read a count metric from metrics first, falling back to profile."""
    v = _first(metrics, *keys)
    if v is None:
        v = _first(profile, *keys)
    return coerce_int(0 if v is None else v)


def _normalize_post(account: dict, post: dict, follower_count: int) -> tuple:
    """Convert one raw socialfetch post dict into a _POST_COLUMNS-aligned tuple."""
    post_id = coerce_str(_first(post, "id", "postId", "pk", "shortcode"))
    raw_type = str(_first(post, "mediaType", "type", "post_type", default="")).lower()
    post_type = POST_TYPE_MAP.get(raw_type)
    caption = _first(post, "caption", "text", "title", default="")
    likes = coerce_int(_first(post, "likeCount", "likes", "diggCount", default=0))
    comments = coerce_int(_first(post, "commentCount", "comments", default=0))
    shares = coerce_int(_first(post, "shareCount", "shares", "repostCount", default=0))
    # videoViewCount is the real IG key; viewCount/views/playCount cover TikTok/YouTube
    views = coerce_int(_first(post, "videoViewCount", "viewCount", "views", "playCount", default=0))
    saves = coerce_int(_first(post, "saveCount", "saves", "bookmarkCount", default=0))
    engagement = likes + comments + shares + saves
    rate = round(engagement / follower_count, 6) if follower_count > 0 else None
    permalink = _first(post, "permalink", "url", "link")
    if permalink is None:
        shortcode = _first(post, "shortcode", "code")
        if shortcode and account.get("platform") == "instagram":
            permalink = f"https://www.instagram.com/p/{shortcode}/"
    published_at = _to_dt(_first(post, "takenAt", "publishedAt", "createTime", "timestamp"))
    return (
        account["account_id"],
        post_id,
        account["platform"],
        published_at,
        post_type,
        caption,
        _first(post, "transcript"),
        likes,
        comments,
        shares,
        views,
        saves,
        rate,
        permalink,
    )


def normalize(account: dict, raw: dict) -> dict:
    """Convert a raw socialfetch payload into DB-ready rows.

    Returns:
        {
            "snapshot": tuple matching _SNAPSHOT_COLUMNS,
            "posts":    list[tuple] each matching _POST_COLUMNS,
            "captions": dict[post_id -> caption text] for the enrichment pass,
        }
    """
    data = raw.get("data") or raw
    profile = data.get("profile") or {}
    metrics = data.get("metrics") or {}
    # recentPosts is the real IG key; fall back to "posts" for test mocks and other platforms
    posts = data.get("recentPosts") or data.get("posts") or profile.get("posts") or []

    follower_count = _count(metrics, profile, "followers", "followerCount", "subscriberCount")
    snapshot = (
        account["account_id"],
        date.today(),
        follower_count,
        _count(metrics, profile, "following", "followingCount"),
        _count(metrics, profile, "posts", "postCount", "mediaCount"),
        _first(profile, "verified", "isVerified"),
    )

    post_rows: list[tuple] = []
    captions: dict[str, str] = {}
    for p in posts:
        row = _normalize_post(account, p, follower_count)
        post_id = row[1]
        if not post_id:
            continue
        post_rows.append(row)
        cap = row[5]
        if cap and str(cap).strip():
            captions[post_id] = str(cap)

    return {"snapshot": snapshot, "posts": post_rows, "captions": captions}
