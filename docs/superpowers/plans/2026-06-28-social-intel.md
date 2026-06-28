# Social Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the dashboard AI assistant learn from Radio Milwaukee's own + competitors' public social accounts by ingesting socialfetch.dev data into a new `social_intel` warehouse schema, Haiku-tagging each post, and exposing it through the assistant's existing `query_sql` tool.

**Architecture:** A Python loader (`load_socialfetch.py`) calls the socialfetch REST API per watchlisted account, normalizes the cross-platform JSON into one snapshot row + N post rows (idempotent `ON CONFLICT` upserts), and a weekly Fly job (`refresh_social_intel.py`) Haiku-tags only the *new* posts. The data reaches the assistant via a `rm_readonly` SELECT grant + the catalog/ask-sql allowlists + a system-prompt section — no new HTTP endpoints. RM's own handles and competitors flow through the identical path, distinguished by an `is_owned` flag.

**Tech Stack:** Python 3.12, psycopg3 (`psycopg==3.3.4`), `requests==2.32.3`, `anthropic==0.69.0` (Haiku tagging), FastAPI catalog endpoints, Postgres on Neon, pytest.

## Global Constraints

- Python 3.12; type hints on function signatures; PEP 8; black/isort/ruff clean.
- psycopg3 only — `import psycopg` (NOT psycopg2). Reuse `loaders/_common.py` helpers (`get_db_connection`, `bulk_upsert`, coercion).
- Every fact table upserts: `ON CONFLICT (<composite_key>) DO UPDATE`. Loaders are pure: `def load(...) -> dict` returning stats, plus a `if __name__ == "__main__"` CLI block. No row-by-row inserts.
- Source schemas are append/upsert-only; never hand-edit fact rows. `loaded_at`/`fetched_at` are audit columns, never in a primary key.
- **Engagement RATE is the headline metric, never raw follower count.** `engagement_rate = (likes + comments + shares + saves) / follower_count_at_fetch`.
- **No commenter PII.** Store aggregate comment *counts* only — never individual commenter rows, names, or handles.
- socialfetch is canonical: REST base `https://api.socialfetch.dev`, header `x-api-key: sfk_...` on every `/v1/**` route. A route can return HTTP 200 with `lookupStatus: "not_found" | "private"` (skip the account, do NOT crash). `402` = out of credits (abort the run + Slack-alert). **Do not invent endpoints or field names** — confirm against `/openapi.json` + `/llms.json` at build time (Task 2 captures a real fixture first).
- Secret `SOCIALFETCH_API_KEY` (`sfk_...`) is already in `~/.radio-milwaukee/.env` (the path `loaders/_common.py` reads). Set it as a Fly secret for the prod job (Task 8).
- Migrations are numbered: `schema/020_social_intel.sql` then `schema/021_social_intel_grant.sql`. Repo is currently at `019`.
- Run backfill/loaders locally with the venv: `source .venv/bin/activate`. Tests: `python -m pytest -q`.

---

### Task 1: `social_intel` schema (4 tables)

**Files:**
- Create: `schema/020_social_intel.sql`
- Test: `tests/test_social_intel_schema.py`

**Interfaces:**
- Produces: tables `social_intel.dim_accounts` (PK `account_id`), `social_intel.fact_account_snapshots` (PK `(account_id, snapshot_date)`), `social_intel.fact_posts` (PK `(account_id, post_id)`), `social_intel.fact_post_enrichment` (PK `post_id`). Column names below are the contract every later task relies on.

- [ ] **Step 1: Write the migration SQL**

Create `schema/020_social_intel.sql`:

```sql
-- schema/020_social_intel.sql
-- Competitive social intelligence. RM's own handles AND competitors flow through
-- ONE pipeline, distinguished by dim_accounts.is_owned. Snapshots are non-additive
-- (query at grain). Enrichment (Haiku tags) is a SEPARATE table from the vendor
-- facts, mirroring email_esp.fact_campaign_content / fact_campaign_enrichment.
-- PII stance: aggregate comment COUNTS only — no commenter rows ever.

CREATE SCHEMA IF NOT EXISTS social_intel;

-- The watchlist / config — the only human-touched table. Add a row, the weekly
-- job tracks it. account_id is our own slug, e.g. 'ig:hyfinmke'.
CREATE TABLE IF NOT EXISTS social_intel.dim_accounts (
    account_id    text PRIMARY KEY,
    platform      text NOT NULL,          -- instagram|tiktok|youtube|facebook|threads|linkedin
    handle        text NOT NULL,
    display_name  text,
    category      text,                   -- peer_station|local_media|music_brand|aspirational|other
    is_owned      boolean NOT NULL DEFAULT false,
    station_code  text,                   -- RM88/HYFIN/RM414/RLR when is_owned, else NULL
    active        boolean NOT NULL DEFAULT true,
    added_at      timestamptz NOT NULL DEFAULT now()
);

-- Profile metrics over time. Non-additive — query at (account_id, snapshot_date).
CREATE TABLE IF NOT EXISTS social_intel.fact_account_snapshots (
    account_id      text NOT NULL REFERENCES social_intel.dim_accounts(account_id),
    snapshot_date   date NOT NULL,
    follower_count  integer NOT NULL DEFAULT 0,
    following_count integer NOT NULL DEFAULT 0,
    post_count      integer NOT NULL DEFAULT 0,
    verified        boolean,
    loaded_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, snapshot_date)
);

-- One row per post. engagement_rate is the comparable metric across account sizes.
-- post_id is the platform-native id (globally unique per platform); the enrichment
-- table keys on it alone so the assistant can join on post_id.
CREATE TABLE IF NOT EXISTS social_intel.fact_posts (
    account_id      text NOT NULL REFERENCES social_intel.dim_accounts(account_id),
    post_id         text NOT NULL,
    platform        text NOT NULL,
    published_at    timestamptz,
    post_type       text,                 -- reel|carousel|image|video|short|text
    caption         text,
    transcript      text,
    likes           integer NOT NULL DEFAULT 0,
    comments_count  integer NOT NULL DEFAULT 0,
    shares          integer NOT NULL DEFAULT 0,
    views           integer NOT NULL DEFAULT 0,
    saves           integer NOT NULL DEFAULT 0,
    engagement_rate numeric,
    permalink       text,
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, post_id)
);

-- Haiku-derived tags per post. Honest-null tags when there's no caption / a failed
-- pass (model='skipped-empty-caption'), exactly like the newsletter enrichment table.
CREATE TABLE IF NOT EXISTS social_intel.fact_post_enrichment (
    post_id          text PRIMARY KEY,
    content_theme    text,                -- local_artist_feature|event_promo|behind_the_scenes|community|music_discovery|...
    format           text,
    primary_topic    text,
    hook_style       text,
    has_cta          boolean,
    featured_artists jsonb NOT NULL DEFAULT '[]'::jsonb,
    enriched_at      timestamptz NOT NULL DEFAULT now(),
    model            text
);

CREATE INDEX IF NOT EXISTS idx_social_posts_account_published
    ON social_intel.fact_posts (account_id, published_at DESC);
```

- [ ] **Step 2: Apply the migration to Neon**

Apply via the Neon MCP `run_sql` against project `morning-frost-30675590`, db `neondb` (run the full file contents). Or locally:

Run: `source .venv/bin/activate && psql "$DATABASE_URL" -f schema/020_social_intel.sql`
Expected: `CREATE SCHEMA`, four `CREATE TABLE`, one `CREATE INDEX`, no errors.

- [ ] **Step 3: Write the failing introspection test**

Create `tests/test_social_intel_schema.py`:

```python
"""Verifies schema/020_social_intel.sql created the expected tables/columns.
Skips when no DATABASE_URL is available (CI without Neon)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

_ENV_PATH = Path.home() / ".radio-milwaukee" / ".env"


def _dsn() -> str | None:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if _ENV_PATH.exists():
        from dotenv import dotenv_values
        return dotenv_values(_ENV_PATH).get("DATABASE_URL")
    return None


pytestmark = pytest.mark.skipif(_dsn() is None, reason="DATABASE_URL not set")


def _columns(table: str) -> set[str]:
    import psycopg
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'social_intel' AND table_name = %s",
            (table,),
        )
        return {r[0] for r in cur.fetchall()}


def test_dim_accounts_columns():
    cols = _columns("dim_accounts")
    assert {"account_id", "platform", "handle", "is_owned", "station_code", "active"} <= cols


def test_fact_posts_has_engagement_rate():
    cols = _columns("fact_posts")
    assert {"account_id", "post_id", "engagement_rate", "comments_count", "caption"} <= cols


def test_fact_post_enrichment_columns():
    cols = _columns("fact_post_enrichment")
    assert {"post_id", "content_theme", "format", "hook_style", "has_cta", "featured_artists"} <= cols
```

- [ ] **Step 4: Run the test to verify it passes (migration already applied)**

Run: `source .venv/bin/activate && python -m pytest tests/test_social_intel_schema.py -v`
Expected: 3 PASS (or 3 SKIP if no DATABASE_URL — acceptable in CI).

- [ ] **Step 5: Commit**

```bash
git add schema/020_social_intel.sql tests/test_social_intel_schema.py
git commit -m "feat(social-intel): add social_intel schema (accounts, snapshots, posts, enrichment)"
```

---

### Task 2: socialfetch REST client + normalizer (`_socialfetch.py`)

**Files:**
- Create: `loaders/_socialfetch.py`
- Create: `tests/fixtures/socialfetch_sample.json` (captured real response, used by tests)
- Test: `tests/test_socialfetch_client.py`

**Interfaces:**
- Consumes: `social_intel.dim_accounts` rows as `dict` (`account_id`, `platform`, `handle`).
- Produces:
  - `fetch_account(account: dict, *, api_key: str, session=None) -> dict | None` — returns the raw socialfetch payload, or `None` when `lookupStatus` is `not_found`/`private`. Raises `SocialfetchCreditError` on HTTP 402.
  - `normalize(account: dict, raw: dict) -> dict` — returns `{"snapshot": tuple, "posts": list[tuple], "captions": dict[str, str]}` where `snapshot` matches `_SNAPSHOT_COLUMNS`, each post tuple matches `_POST_COLUMNS`, and `captions` maps `post_id -> caption text` for the enrichment pass.
  - Module constants `_SNAPSHOT_COLUMNS`, `_POST_COLUMNS`, `POST_TYPE_MAP`, `SocialfetchCreditError`.

- [ ] **Step 1: Capture a real socialfetch response as a test fixture (build-time confirmation)**

This step confirms the live contract so the normalizer is written against real keys, not guesses. With `SOCIALFETCH_API_KEY` in `~/.radio-milwaukee/.env`, fetch the API contract and one real account, then save the response:

```bash
source .venv/bin/activate
# 1. Read the contract to learn exact routes + field names:
curl -s https://api.socialfetch.dev/openapi.json | python -m json.tool | less
curl -s https://api.socialfetch.dev/llms.json   | python -m json.tool | less
# 2. Capture ONE real account (use an RM-owned handle; adjust route per /openapi.json):
mkdir -p tests/fixtures
python - <<'PY'
import json, os
from pathlib import Path
from dotenv import dotenv_values
import requests
key = (os.environ.get("SOCIALFETCH_API_KEY")
       or dotenv_values(Path.home()/".radio-milwaukee"/".env").get("SOCIALFETCH_API_KEY"))
# CONFIRM the exact path + params against /openapi.json before running:
r = requests.get("https://api.socialfetch.dev/v1/instagram/profile",
                 params={"handle": "hyfinmke"},
                 headers={"x-api-key": key}, timeout=30)
print("HTTP", r.status_code)
Path("tests/fixtures/socialfetch_sample.json").write_text(json.dumps(r.json(), indent=2))
PY
```

Open `tests/fixtures/socialfetch_sample.json` and note the **exact** key names for: follower count, following count, post count, verified flag, the posts array, and per-post id/type/caption/likes/comments/shares/views/saves/published timestamp/permalink. These fill the `_first(...)` candidate lists in Step 3. Keep this fixture in the repo — the tests read it.

- [ ] **Step 2: Write the failing test**

Create `tests/test_socialfetch_client.py`:

```python
import json, os, sys
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
    post_ids = {r[1] for r in out["posts"]}      # (account_id, post_id, ...)
    assert set(out["captions"]).issubset(post_ids)


def test_engagement_rate_uses_followers_at_fetch():
    raw = {"lookupStatus": "ok", "data": {
        "profile": {"followerCount": 100},
        "posts": [{"id": "p1", "likeCount": 8, "commentCount": 2, "shareCount": 0, "saveCount": 0}],
    }}
    out = sf.normalize(ACCOUNT, raw)
    er_index = sf._POST_COLUMNS.index("engagement_rate")
    assert out["posts"][0][er_index] == pytest.approx(0.10)   # (8+2)/100


def test_normalize_zero_followers_yields_null_rate():
    raw = {"lookupStatus": "ok", "data": {
        "profile": {"followerCount": 0},
        "posts": [{"id": "p1", "likeCount": 5}],
    }}
    out = sf.normalize(ACCOUNT, raw)
    er_index = sf._POST_COLUMNS.index("engagement_rate")
    assert out["posts"][0][er_index] is None   # no divide-by-zero
```

- [ ] **Step 3: Write the client + normalizer**

Create `loaders/_socialfetch.py`. The `_first()` helper tolerates the cross-platform key variations socialfetch returns; fill its candidate lists from the fixture captured in Step 1.

```python
"""socialfetch.dev REST client + cross-platform normalizer.

REST base https://api.socialfetch.dev, header `x-api-key: sfk_...` on every /v1/**.
Routes + field names are confirmed against /openapi.json + /llms.json and the
captured fixture tests/fixtures/socialfetch_sample.json. A 200 response can still
be lookupStatus not_found/private (return None, skip). HTTP 402 = out of credits
(raise SocialfetchCreditError so the job aborts + alerts).
"""
from __future__ import annotations

import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from _common import coerce_int, coerce_str  # noqa: E402

import requests

_BASE = "https://api.socialfetch.dev"
_TIMEOUT_SEC = 30

# CONFIRM these route templates against /openapi.json. socialfetch returns profile
# + recent posts; if it is one endpoint, set _POSTS_ROUTE = None and read posts
# from the profile payload in normalize().
_PROFILE_ROUTE = "/v1/{platform}/profile"   # params: handle
_POSTS_ROUTE: str | None = None             # None => posts ride inside the profile payload

# Raw socialfetch post_type/media_type -> our closed vocab.
POST_TYPE_MAP = {
    "reel": "reel", "clip": "reel",
    "carousel": "carousel", "album": "carousel", "sidecar": "carousel",
    "image": "image", "photo": "image", "picture": "image",
    "video": "video",
    "short": "short", "shorts": "short",
    "text": "text", "status": "text", "tweet": "text",
}

_SNAPSHOT_COLUMNS = [
    "account_id", "snapshot_date", "follower_count", "following_count",
    "post_count", "verified",
]
_POST_COLUMNS = [
    "account_id", "post_id", "platform", "published_at", "post_type",
    "caption", "transcript", "likes", "comments_count", "shares", "views",
    "saves", "engagement_rate", "permalink",
]


class SocialfetchCreditError(RuntimeError):
    """HTTP 402 — socialfetch credits exhausted; abort the run."""


def _first(d: dict, *keys, default=None):
    """Return the first present, non-None value among candidate keys."""
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return default


def fetch_account(account: dict, *, api_key: str, session=None) -> dict | None:
    """Fetch one account's profile (+ recent posts). None => skip (not_found/private)."""
    http = session or requests
    headers = {"x-api-key": api_key}
    url = _BASE + _PROFILE_ROUTE.format(platform=account["platform"])
    resp = http.get(url, headers=headers, params={"handle": account["handle"]},
                    timeout=_TIMEOUT_SEC)
    if resp.status_code == 402:
        raise SocialfetchCreditError(f"402 for {account['account_id']}")
    payload = resp.json()
    status = (payload.get("lookupStatus") or "").lower()
    if status in ("not_found", "private"):
        return None
    return payload


def _normalize_post(account: dict, post: dict, follower_count: int) -> tuple:
    post_id = coerce_str(_first(post, "id", "postId", "pk", "shortcode"))
    raw_type = str(_first(post, "type", "mediaType", "post_type", default="")).lower()
    post_type = POST_TYPE_MAP.get(raw_type)
    caption = _first(post, "caption", "text", "title", default="")
    likes = coerce_int(_first(post, "likeCount", "likes", "diggCount", default=0))
    comments = coerce_int(_first(post, "commentCount", "comments", default=0))
    shares = coerce_int(_first(post, "shareCount", "shares", "repostCount", default=0))
    views = coerce_int(_first(post, "viewCount", "views", "playCount", default=0))
    saves = coerce_int(_first(post, "saveCount", "saves", "bookmarkCount", default=0))
    engagement = likes + comments + shares + saves
    rate = round(engagement / follower_count, 6) if follower_count > 0 else None
    return (
        account["account_id"],
        post_id,
        account["platform"],
        _first(post, "publishedAt", "takenAt", "createTime", "timestamp"),
        post_type,
        caption,
        _first(post, "transcript"),
        likes, comments, shares, views, saves,
        rate,
        _first(post, "permalink", "url", "link"),
    )


def normalize(account: dict, raw: dict) -> dict:
    """raw socialfetch payload -> {snapshot tuple, posts list[tuple], captions dict}."""
    data = raw.get("data") or raw
    profile = data.get("profile") or data
    posts = data.get("posts") or profile.get("posts") or []

    follower_count = coerce_int(_first(profile, "followerCount", "followers", "subscriberCount", default=0))
    snapshot = (
        account["account_id"],
        date.today(),
        follower_count,
        coerce_int(_first(profile, "followingCount", "following", default=0)),
        coerce_int(_first(profile, "postCount", "posts", "mediaCount", default=0)),
        _first(profile, "verified", "isVerified"),
    )

    post_rows, captions = [], {}
    for p in posts:
        row = _normalize_post(account, p, follower_count)
        post_id = row[1]
        if not post_id:
            continue
        post_rows.append(row)
        caption = row[5]
        if caption and str(caption).strip():
            captions[post_id] = str(caption)
    return {"snapshot": snapshot, "posts": post_rows, "captions": captions}
```

- [ ] **Step 4: Run the tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_socialfetch_client.py -v`
Expected: all PASS. If `test_normalize_real_fixture_shapes` fails on key extraction, adjust the `_first(...)` candidate lists to the exact keys in `tests/fixtures/socialfetch_sample.json` (this is the build-time confirmation, not a guess).

- [ ] **Step 5: Commit**

```bash
git add loaders/_socialfetch.py tests/test_socialfetch_client.py tests/fixtures/socialfetch_sample.json
git commit -m "feat(social-intel): socialfetch REST client + cross-platform normalizer"
```

---

### Task 3: social post enrichment taxonomy (`_social_enrich.py`)

**Files:**
- Create: `loaders/_social_enrich.py`
- Test: `tests/test_social_enrich.py`

**Interfaces:**
- Consumes: a caption string + an `anthropic` client.
- Produces:
  - `validate_enrichment(raw: dict) -> dict` with keys `content_theme`, `format`, `primary_topic`, `hook_style`, `has_cta`, `featured_artists` (out-of-vocab values nulled, artists deduped/capped).
  - `enrich_post(client, caption: str, *, model: str = "claude-haiku-4-5-20251001") -> dict` — one Haiku pass, returns a validated dict.
  - Vocab constants `CONTENT_THEMES`, `FORMATS`, `HOOK_STYLES`, `TOPICS`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_social_enrich.py`:

```python
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "loaders"))

import _social_enrich as se


def test_validate_drops_out_of_vocab_and_dedups_artists():
    raw = {"content_theme": "local_artist_feature", "format": "reel",
           "primary_topic": "music_discovery", "hook_style": "question",
           "has_cta": True, "featured_artists": ["Klassik", "Klassik", "  GGOOLD "]}
    out = se.validate_enrichment(raw)
    assert out["content_theme"] == "local_artist_feature"
    assert out["format"] == "reel"
    assert out["has_cta"] is True
    assert out["featured_artists"] == ["Klassik", "GGOOLD"]


def test_validate_nulls_invalid_scalars():
    out = se.validate_enrichment({"content_theme": "nope", "format": "bogus",
                                  "primary_topic": "nope", "hook_style": "nope",
                                  "has_cta": "yes", "featured_artists": None})
    assert out == {"content_theme": None, "format": None, "primary_topic": None,
                   "hook_style": None, "has_cta": None, "featured_artists": []}


def test_enrich_post_uses_injected_client_and_validates():
    class FakeBlock:
        type = "tool_use"
        input = {"content_theme": "event_promo", "format": "image",
                 "primary_topic": "events", "hook_style": "announcement",
                 "has_cta": True, "featured_artists": ["junk", "Foo"]}
    class FakeResp:
        content = [FakeBlock()]
    class FakeClient:
        def __init__(self): self.messages = self
        def create(self, **kw):
            assert kw["tool_choice"]["name"] == "record_post_enrichment"
            return FakeResp()
    out = se.enrich_post(FakeClient(), "Big show this Friday — tickets in bio!")
    assert out["content_theme"] == "event_promo"
    assert out["has_cta"] is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_social_enrich.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named '_social_enrich'`.

- [ ] **Step 3: Write the enrichment module**

Create `loaders/_social_enrich.py` (mirrors `loaders/_enrich.py`):

```python
"""LLM enrichment of a social post caption into structured, closed-vocab tags.

One Haiku pass per post. The taxonomy here is the single source of truth;
validate_enrichment drops anything the model invents so GROUP BY stays clean.
Mirrors loaders/_enrich.py (newsletter enrichment).
"""
from __future__ import annotations

CONTENT_THEMES = {
    "local_artist_feature", "event_promo", "behind_the_scenes", "community",
    "music_discovery", "station_news", "contest_giveaway", "membership_giving",
    "partnership", "other",
}
FORMATS = {"reel", "carousel", "image", "video", "short", "text", "story"}
HOOK_STYLES = {"question", "bold_claim", "announcement", "listicle",
               "storytelling", "callout", "none"}
TOPICS = {"local_music", "artist_spotlight", "music_discovery", "events",
          "membership_giving", "station_news", "community", "partnerships",
          "podcasts", "contests"}

_MAX_ARTISTS = 20

ENRICH_TOOL = {
    "name": "record_post_enrichment",
    "description": "Record structured tags for one social media post.",
    "input_schema": {
        "type": "object",
        "properties": {
            "content_theme": {"type": "string", "enum": sorted(CONTENT_THEMES),
                              "description": "The single best-fit theme of the post."},
            "format": {"type": "string", "enum": sorted(FORMATS)},
            "primary_topic": {"type": "string", "enum": sorted(TOPICS)},
            "hook_style": {"type": "string", "enum": sorted(HOOK_STYLES),
                           "description": "The opening device of the caption."},
            "has_cta": {"type": "boolean",
                        "description": "True if the post asks the viewer to act (link in bio, tickets, donate, follow)."},
            "featured_artists": {"type": "array", "items": {"type": "string"},
                                 "description": "Proper names of musicians/bands actually mentioned."},
        },
        "required": ["content_theme", "format", "primary_topic", "hook_style",
                     "has_cta", "featured_artists"],
    },
}

_PROMPT = (
    "You tag social media posts for Radio Milwaukee's competitive intelligence. "
    "Read the caption and call record_post_enrichment with the closed-vocabulary "
    "tags. Use only the allowed enum values; if unsure of a field, choose the "
    "closest allowed value (or 'other'/'none'). featured_artists are proper names "
    "of musicians/bands actually mentioned.\n\nPost caption:\n"
)


def validate_enrichment(raw: dict) -> dict:
    raw = raw or {}
    ct = raw.get("content_theme")
    fmt = raw.get("format")
    pt = raw.get("primary_topic")
    hook = raw.get("hook_style")
    cta = raw.get("has_cta")
    artists_in = raw.get("featured_artists") if isinstance(raw.get("featured_artists"), list) else []

    artists, seen = [], set()
    for a in artists_in:
        if not isinstance(a, str):
            continue
        name = a.strip()
        if name and name not in seen:
            seen.add(name)
            artists.append(name)
    return {
        "content_theme": ct if ct in CONTENT_THEMES else None,
        "format": fmt if fmt in FORMATS else None,
        "primary_topic": pt if pt in TOPICS else None,
        "hook_style": hook if hook in HOOK_STYLES else None,
        "has_cta": cta if isinstance(cta, bool) else None,
        "featured_artists": artists[:_MAX_ARTISTS],
    }


def enrich_post(client, caption: str, *, model: str = "claude-haiku-4-5-20251001") -> dict:
    """Run one enrichment pass; returns a validated enrichment dict."""
    resp = client.messages.create(
        model=model,
        max_tokens=512,
        tools=[ENRICH_TOOL],
        tool_choice={"type": "tool", "name": "record_post_enrichment"},
        messages=[{"role": "user", "content": _PROMPT + (caption or "")[:8000]}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return validate_enrichment(block.input)
    return validate_enrichment({})
```

- [ ] **Step 4: Run the tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_social_enrich.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add loaders/_social_enrich.py tests/test_social_enrich.py
git commit -m "feat(social-intel): Haiku post-enrichment taxonomy + validator"
```

---

### Task 4: loader (`load_socialfetch.py`)

**Files:**
- Create: `loaders/load_socialfetch.py`
- Test: `tests/test_load_socialfetch.py`

**Interfaces:**
- Consumes: `_socialfetch.fetch_account`/`normalize`, `_social_enrich.enrich_post`/`validate_enrichment`, `_common.get_db_connection`/`bulk_upsert`.
- Produces: `load(account: dict, *, api_key=None, enrich=True, client=None, model=None, conn=None) -> dict` returning `{"account_id", "skipped", "posts_total", "posts_upserted", "snapshots_upserted", "enriched", "elapsed_sec"}`. Upserts 1 snapshot row + N `fact_posts` (`ON CONFLICT (account_id, post_id) DO UPDATE`) and enriches only posts with no `fact_post_enrichment` row.

- [ ] **Step 1: Write the failing test**

Create `tests/test_load_socialfetch.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_load_socialfetch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'load_socialfetch'`.

- [ ] **Step 3: Write the loader**

Create `loaders/load_socialfetch.py`:

```python
"""Fetch one social account from socialfetch, upsert its snapshot + posts, and
Haiku-tag any post that has no enrichment row yet.

Pure + idempotent: ON CONFLICT (account_id, snapshot_date) and (account_id, post_id)
DO UPDATE. Only NEW posts (no enrichment row) hit the LLM, so weekly cost stays flat.

CLI:
  python loaders/load_socialfetch.py ig:hyfinmke instagram hyfinmke
  python loaders/load_socialfetch.py ig:hyfinmke instagram hyfinmke --no-enrich
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db_connection, bulk_upsert  # noqa: E402
from _socialfetch import (  # noqa: E402
    fetch_account, normalize, _SNAPSHOT_COLUMNS, _POST_COLUMNS,
)
from _social_enrich import enrich_post, validate_enrichment  # noqa: E402

SNAPSHOT_TABLE = "social_intel.fact_account_snapshots"
POSTS_TABLE = "social_intel.fact_posts"
ENRICH_TABLE = "social_intel.fact_post_enrichment"
DEFAULT_MODEL = os.environ.get("ENRICH_MODEL", "claude-haiku-4-5-20251001")

_ENRICH_COLUMNS = ["post_id", "content_theme", "format", "primary_topic",
                   "hook_style", "has_cta", "featured_artists", "model"]


def _anthropic_client():
    import anthropic
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY


def _already_enriched(conn, post_ids: list[str]) -> set[str]:
    """Return the subset of post_ids that already have an enrichment row."""
    if not post_ids:
        return set()
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT post_id FROM {ENRICH_TABLE} WHERE post_id = ANY(%s)",
            (list(post_ids),),
        )
        return {r[0] for r in cur.fetchall()}


def load(account: dict, *, api_key=None, enrich=True, client=None,
         model=None, conn=None) -> dict:
    start = time.time()
    api_key = api_key or os.environ["SOCIALFETCH_API_KEY"]
    model = model or DEFAULT_MODEL
    owns_conn = conn is None
    conn = conn or get_db_connection()
    try:
        raw = fetch_account(account, api_key=api_key)
        if raw is None:                        # not_found / private — skip cleanly
            return {"account_id": account["account_id"], "skipped": True,
                    "posts_total": 0, "posts_upserted": 0, "snapshots_upserted": 0,
                    "enriched": 0, "elapsed_sec": round(time.time() - start, 1)}

        norm = normalize(account, raw)
        snap_upserted = bulk_upsert(
            conn, SNAPSHOT_TABLE, _SNAPSHOT_COLUMNS, [norm["snapshot"]],
            ["account_id", "snapshot_date"],
            [c for c in _SNAPSHOT_COLUMNS if c not in ("account_id", "snapshot_date")],
        )
        posts_upserted = bulk_upsert(
            conn, POSTS_TABLE, _POST_COLUMNS, norm["posts"],
            ["account_id", "post_id"],
            [c for c in _POST_COLUMNS if c not in ("account_id", "post_id")],
        )

        enrich_rows = []
        if enrich and norm["captions"]:
            new_ids = set(norm["captions"]) - _already_enriched(conn, list(norm["captions"]))
            if new_ids and client is None:
                client = _anthropic_client()
            for post_id in sorted(new_ids):
                tags = enrich_post(client, norm["captions"][post_id], model=model)
                tags = validate_enrichment(tags)   # defensive: stub may return raw
                enrich_rows.append((
                    post_id, tags["content_theme"], tags["format"],
                    tags["primary_topic"], tags["hook_style"], tags["has_cta"],
                    json.dumps(tags["featured_artists"]), model,
                ))
            if enrich_rows:
                bulk_upsert(
                    conn, ENRICH_TABLE, _ENRICH_COLUMNS, enrich_rows, ["post_id"],
                    [c for c in _ENRICH_COLUMNS if c != "post_id"],
                )
        return {"account_id": account["account_id"], "skipped": False,
                "posts_total": len(norm["posts"]), "posts_upserted": posts_upserted,
                "snapshots_upserted": snap_upserted, "enriched": len(enrich_rows),
                "elapsed_sec": round(time.time() - start, 1)}
    finally:
        if owns_conn:
            conn.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    enrich = "--no-enrich" not in args
    pos = [a for a in args if not a.startswith("--")]
    if len(pos) < 3:
        raise SystemExit("usage: load_socialfetch.py <account_id> <platform> <handle> [--no-enrich]")
    acct = {"account_id": pos[0], "platform": pos[1], "handle": pos[2]}
    print(load(acct, enrich=enrich))
```

- [ ] **Step 4: Run the tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_load_socialfetch.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add loaders/load_socialfetch.py tests/test_load_socialfetch.py
git commit -m "feat(social-intel): per-account loader (snapshot + posts + new-post enrichment)"
```

---

### Task 5: weekly job (`refresh_social_intel.py`)

**Files:**
- Create: `jobs/refresh_social_intel.py`
- Test: `tests/test_refresh_social_intel.py`

**Interfaces:**
- Consumes: `load_socialfetch.load`, `_common.get_db_connection`, `_socialfetch.SocialfetchCreditError`, `service.slack.post_success`/`post_failure`.
- Produces: `active_accounts(conn) -> list[dict]`, `run() -> dict` (summary `{accounts, fetched, skipped, posts_new, enriched, failures, tag}`; posts Slack success; on `SocialfetchCreditError` aborts + posts failure + re-raises).

- [ ] **Step 1: Write the failing test**

Create `tests/test_refresh_social_intel.py`:

```python
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "jobs"))
sys.path.insert(0, os.path.join(ROOT, "loaders"))
sys.path.insert(0, ROOT)

import pytest
import refresh_social_intel as job
import _socialfetch as sf

ACCOUNTS = [
    {"account_id": "ig:a", "platform": "instagram", "handle": "a"},
    {"account_id": "ig:b", "platform": "instagram", "handle": "b"},
]


def _setup(monkeypatch, load_side_effect):
    monkeypatch.setattr(job, "get_db_connection", lambda: object())
    monkeypatch.setattr(job, "active_accounts", lambda conn: list(ACCOUNTS))
    monkeypatch.setattr(job, "load", load_side_effect)


def test_run_aggregates_and_posts_success(monkeypatch):
    def fake_load(account, *, conn):
        return {"account_id": account["account_id"], "skipped": False,
                "posts_total": 3, "posts_upserted": 3, "snapshots_upserted": 1,
                "enriched": 2, "elapsed_sec": 1.0}
    _setup(monkeypatch, fake_load)
    posted = {}
    monkeypatch.setattr(job, "post_success", lambda tag, stats: posted.setdefault("ok", (tag, stats)))
    monkeypatch.setattr(job, "post_failure", lambda tag, err: posted.setdefault("fail", (tag, err)))

    out = job.run()
    assert out["tag"] == "[SOCIAL-INTEL]"
    assert out["accounts"] == 2 and out["fetched"] == 2
    assert out["posts_new"] == 6 and out["enriched"] == 4
    assert posted["ok"][0] == "[SOCIAL-INTEL]"
    assert "fail" not in posted


def test_run_isolates_one_bad_handle(monkeypatch):
    def fake_load(account, *, conn):
        if account["account_id"] == "ig:b":
            raise RuntimeError("boom")
        return {"account_id": "ig:a", "skipped": False, "posts_total": 1,
                "posts_upserted": 1, "snapshots_upserted": 1, "enriched": 0, "elapsed_sec": 1.0}
    _setup(monkeypatch, fake_load)
    monkeypatch.setattr(job, "post_success", lambda tag, stats: None)
    monkeypatch.setattr(job, "post_failure", lambda tag, err: None)

    out = job.run()
    assert out["fetched"] == 1            # the good account still landed
    assert out["failures"] == 1          # the bad one is counted, not fatal


def test_run_aborts_on_credit_error(monkeypatch):
    def fake_load(account, *, conn):
        raise sf.SocialfetchCreditError("402")
    _setup(monkeypatch, fake_load)
    posted = {}
    monkeypatch.setattr(job, "post_success", lambda tag, stats: posted.setdefault("ok", 1))
    monkeypatch.setattr(job, "post_failure", lambda tag, err: posted.setdefault("fail", err))

    with pytest.raises(sf.SocialfetchCreditError):
        job.run()
    assert "fail" in posted and "ok" not in posted
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_refresh_social_intel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'refresh_social_intel'`.

- [ ] **Step 3: Write the job**

Create `jobs/refresh_social_intel.py` (mirrors `jobs/refresh_mailchimp_content.py`, but loops accounts):

```python
"""Weekly sweep: fetch every active watchlist account, upsert snapshot + posts,
Haiku-tag new posts. One bad handle never aborts the run; a socialfetch credit
exhaustion (402) DOES abort + alerts so we notice immediately.

Fly scheduled machine `social-intel-weekly`. CLI:
  python jobs/refresh_social_intel.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "loaders"))
sys.path.insert(0, ROOT)
from _common import get_db_connection  # noqa: E402
from _socialfetch import SocialfetchCreditError  # noqa: E402
from load_socialfetch import load  # noqa: E402
from service.slack import post_success, post_failure  # noqa: E402

TAG = "[SOCIAL-INTEL]"


def active_accounts(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT account_id, platform, handle FROM social_intel.dim_accounts "
            "WHERE active ORDER BY account_id"
        )
        return [{"account_id": r[0], "platform": r[1], "handle": r[2]}
                for r in cur.fetchall()]


def run() -> dict:
    conn = get_db_connection()
    summary = {"accounts": 0, "fetched": 0, "skipped": 0, "posts_new": 0,
               "enriched": 0, "failures": 0, "tag": TAG}
    try:
        accounts = active_accounts(conn)
        summary["accounts"] = len(accounts)
        for account in accounts:
            try:
                stats = load(account, conn=conn)
                if stats["skipped"]:
                    summary["skipped"] += 1
                else:
                    summary["fetched"] += 1
                    summary["posts_new"] += stats["posts_upserted"]
                    summary["enriched"] += stats["enriched"]
            except SocialfetchCreditError:
                # Out of credits — every later account would fail too. Abort loudly.
                post_failure(TAG, "socialfetch credits exhausted (402) — run aborted")
                raise
            except Exception as exc:            # noqa: BLE001 — isolate one bad handle
                summary["failures"] += 1
                print(f"{TAG} skipped {account['account_id']}: {exc}")
        # Shape the success message for service.slack.post_success.
        post_success(TAG, {"table": "social_intel.fact_posts",
                           "rows_upserted": summary["posts_new"],
                           "rows_read": summary["accounts"],
                           "elapsed_sec": "—"})
        return summary
    finally:
        conn.close()


if __name__ == "__main__":
    print(run())
```

- [ ] **Step 4: Run the tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_refresh_social_intel.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add jobs/refresh_social_intel.py tests/test_refresh_social_intel.py
git commit -m "feat(social-intel): weekly Fly job (per-account isolation, credit-abort, Slack)"
```

---

### Task 6: grant migration + catalog/ask-sql allowlists

**Files:**
- Create: `schema/021_social_intel_grant.sql`
- Modify: `service/catalog_api.py` (`_ALLOWED_SCHEMAS`, `_DIMENSION_COLUMNS`, `_TABLE_NOTES`)
- Modify: `service/ask_sql_api.py` (`ALLOWED_SCHEMAS`)
- Test: `tests/test_catalog_endpoints.py` (add cases), `tests/test_ask_sql.py` (add case)

**Interfaces:**
- Consumes: `social_intel.*` tables (Task 1), `rm_readonly` role (schema/016).
- Produces: `rm_readonly` SELECT on all `social_intel` tables; `social_intel` in both allowlists; `content_theme`/`format`/`hook_style`/`primary_topic` value-enumerable.

- [ ] **Step 1: Write the grant migration**

Create `schema/021_social_intel_grant.sql`:

```sql
-- schema/021_social_intel_grant.sql
-- Grant the assistant's read-only role SELECT on social_intel. No PII lives here
-- (aggregate comment COUNTS only — no commenter rows), so plain table-level grants
-- are fine (simpler than the column-level funraise grant in schema/018).
--
-- No ALTER DEFAULT PRIVILEGES: a future social_intel table is granted explicitly.

GRANT USAGE ON SCHEMA social_intel TO rm_readonly;

GRANT SELECT ON social_intel.dim_accounts           TO rm_readonly;
GRANT SELECT ON social_intel.fact_account_snapshots TO rm_readonly;
GRANT SELECT ON social_intel.fact_posts             TO rm_readonly;
GRANT SELECT ON social_intel.fact_post_enrichment   TO rm_readonly;
```

- [ ] **Step 2: Apply the migration to Neon**

Apply via Neon MCP `run_sql` (project `morning-frost-30675590`), or:
Run: `source .venv/bin/activate && psql "$DATABASE_URL" -f schema/021_social_intel_grant.sql`
Expected: `GRANT` ×5, no errors.

- [ ] **Step 3: Write the failing allowlist tests**

Add to `tests/test_catalog_endpoints.py` (inside `class TestGetSchema`):

```python
    def test_schema_catalog_includes_social_intel_in_allowed_set(self):
        """Unit-level guard: catalog_api._ALLOWED_SCHEMAS includes social_intel."""
        from service.catalog_api import _ALLOWED_SCHEMAS
        assert "social_intel" in _ALLOWED_SCHEMAS

    @pytest.mark.skipif(not _db_available(), reason="DATABASE_URL not set")
    def test_social_intel_schema_present(self):
        r = client.get("/api/schema")
        schemas = {e["schema"] for e in r.json()}
        assert "social_intel" in schemas, f"social_intel not found: {schemas}"

    def test_enrich_allows_social_content_theme(self):
        """Unit: content_theme IS a curated dimension and gets enumerated."""
        from service.catalog_api import _enrich_distinct_values

        class _FakeCur:
            def execute(self, *a, **k): pass
            def fetchall(self):
                return [{"v": "event_promo", "n": 9}, {"v": "community", "n": 4}]

        col = {"name": "content_theme", "type": "text"}
        _enrich_distinct_values(_FakeCur(), "social_intel", "fact_post_enrichment", col)
        assert col.get("values") == ["event_promo", "community"]

    def test_enrich_does_not_enumerate_caption(self):
        """Unit: caption is free text (PII-ish) — never enumerated."""
        from service.catalog_api import _enrich_distinct_values
        col = {"name": "caption", "type": "text"}
        _enrich_distinct_values(None, "social_intel", "fact_posts", col)
        assert "values" not in col
```

Add to `tests/test_ask_sql.py`:

```python
def test_social_intel_schema_is_allowed():
    from service.ask_sql_api import validate_sql
    # Should not raise — social_intel is on the allowlist.
    out = validate_sql(
        "SELECT account_id, engagement_rate FROM social_intel.fact_posts"
    )
    assert "social_intel.fact_posts" in out
```

- [ ] **Step 4: Run to verify the new tests fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_catalog_endpoints.py::TestGetSchema::test_schema_catalog_includes_social_intel_in_allowed_set tests/test_ask_sql.py::test_social_intel_schema_is_allowed -v`
Expected: FAIL (`social_intel` not yet in the allowlists).

- [ ] **Step 5: Add `social_intel` to both allowlists**

In `service/catalog_api.py`, edit `_ALLOWED_SCHEMAS`:

```python
_ALLOWED_SCHEMAS: frozenset[str] = frozenset({
    "wms", "nielsen", "ga", "meta_organic", "meta_ads",
    "email_esp", "finance", "dim", "marts", "funraise", "social_intel",
})
```

In `service/catalog_api.py`, extend `_DIMENSION_COLUMNS` — add these to the set (alongside the existing `category`/`platform`/`post_type` already present):

```python
    # social_intel enrichment — closed-vocab tags, safe to enumerate
    "content_theme", "format", "hook_style", "primary_topic",
```

In `service/ask_sql_api.py`, edit `ALLOWED_SCHEMAS`:

```python
ALLOWED_SCHEMAS: frozenset[str] = frozenset({
    "wms", "nielsen", "ga", "meta_organic", "meta_ads",
    "email_esp", "finance", "dim", "marts", "funraise", "social_intel",
})
```

- [ ] **Step 6: Add per-table notes**

In `service/catalog_api.py`, add to `_TABLE_NOTES`:

```python
    ("social_intel", "dim_accounts"): (
        "Watchlist of social accounts we track. `is_owned`=true is Radio Milwaukee, "
        "false is a COMPETITOR/peer. `category` (peer_station/local_media/music_brand/"
        "aspirational), `platform`, `station_code` when owned. Join to fact_posts / "
        "fact_account_snapshots on account_id."
    ),
    ("social_intel", "fact_account_snapshots"): (
        "Profile metrics over time per (account_id, snapshot_date) — follower_count, "
        "post_count. Weekly. follower_count is a VANITY number; compare with engagement_rate "
        "on fact_posts, not raw followers. Non-additive — query at the snapshot grain."
    ),
    ("social_intel", "fact_posts"): (
        "One row per public post per (account_id, post_id). USE `engagement_rate` "
        "(=(likes+comments+shares+saves)/followers-at-fetch) — it is comparable across "
        "account sizes; do NOT rank by raw likes/followers. Aggregate comment COUNTS only "
        "(no commenter data). Join dim_accounts on account_id to split us (is_owned) vs them; "
        "join fact_post_enrichment on post_id for content tags. Recent posts only (no deep history)."
    ),
    ("social_intel", "fact_post_enrichment"): (
        "Haiku-derived TAGS per post (PK post_id). `content_theme` (local_artist_feature/"
        "event_promo/behind_the_scenes/community/music_discovery/...), `format`, `hook_style`, "
        "`has_cta`, `featured_artists` (jsonb). Join fact_posts on post_id to ask 'what "
        "themes/formats drive engagement_rate?'. model='skipped-empty-caption' => no caption to tag."
    ),
```

- [ ] **Step 7: Run the full catalog + ask-sql suites**

Run: `source .venv/bin/activate && python -m pytest tests/test_catalog_endpoints.py tests/test_ask_sql.py -v`
Expected: all PASS (live `social_intel`-present test PASSES because Task 1/Task 6 migrations are applied; SKIPS if no DATABASE_URL).

- [ ] **Step 8: Commit**

```bash
git add schema/021_social_intel_grant.sql service/catalog_api.py service/ask_sql_api.py tests/test_catalog_endpoints.py tests/test_ask_sql.py
git commit -m "feat(social-intel): grant rm_readonly + catalog/ask-sql allowlist + table notes"
```

---

### Task 7: system prompt — competitive social intelligence section

**Files:**
- Modify: `dashboard/api/system-prompt.md` (data-sources list + a new section + retrieval note)

**Interfaces:**
- Consumes: the `social_intel` tables + the engagement-rate framing. No code; this is the assistant's behavioral contract.

- [ ] **Step 1: Add a data-sources bullet**

In `dashboard/api/system-prompt.md`, under `## Data sources and access`, add after the existing Social (Meta) bullet (line ~98):

```markdown
- **Competitive social intelligence (`social_intel.*`)** — public social posts for Radio Milwaukee's OWN handles AND tracked competitors/peers, one pipeline distinguished by `dim_accounts.is_owned`. `fact_posts` carries each post's `engagement_rate` (the comparable metric across account sizes), `fact_post_enrichment` carries Haiku content tags (`content_theme`, `format`, `hook_style`, `has_cta`). Recent posts only — a rolling window, not full history. Use it to answer "how does our social compare?" and "what kind of content is working (for us and for them)?"
```

- [ ] **Step 2: Add the behavioral section**

In `dashboard/api/system-prompt.md`, add a new section after `## Public media metrics — speak the language` block (before `## How to communicate`):

```markdown
## Competitive social intelligence

You can compare Radio Milwaukee's social performance against tracked competitors and peers using `social_intel.*` (via `query_sql`). How to reason about it:

- **Engagement RATE, never vanity followers.** Rank and compare on `fact_posts.engagement_rate` (engagement ÷ followers-at-fetch), which is fair across account sizes. A small account with a high rate is outperforming a big one with a low rate. Never lead with raw follower count.
- **Separate us from them.** `dim_accounts.is_owned = true` is Radio Milwaukee; `false` is a competitor/peer. Always make the comparison explicit ("our reels average X%, the peer set averages Y%").
- **Learn from the content tags, don't just count.** Join `fact_posts` to `fact_post_enrichment` on `post_id` to see WHAT works: "their top-engaging posts skew local-artist features + behind-the-scenes; ours skew event promos — consider shifting the mix." That recommendation is the point, not the raw numbers.
- **Frame as actionable recommendations** for the social/marketing team — formats to try, themes that resonate, cadence gaps.
- **Be honest about the window.** This is recent public data on a rolling basis, not a full historical archive, and it covers only the accounts on the watchlist. Say so when it matters.
```

- [ ] **Step 3: Add a `query_sql` reminder note**

In `dashboard/api/system-prompt.md`, in `## How you retrieve data`, append to the `query_sql` bullet (line ~136), after the existing sentence:

```markdown
 It also reaches `social_intel.*` (competitive social benchmarks) — reason in engagement rate, not follower count, and split owned vs competitor via `is_owned`.
```

- [ ] **Step 4: Verify the edits render and reference real columns**

Run: `grep -n "social_intel\|engagement_rate\|is_owned" dashboard/api/system-prompt.md`
Expected: matches in the data-sources bullet, the new section, and the retrieval note — all column names match `schema/020_social_intel.sql`.

- [ ] **Step 5: Commit**

```bash
git add dashboard/api/system-prompt.md
git commit -m "docs(social-intel): system-prompt competitive social intelligence section"
```

---

### Task 8: seed watchlist + deploy runbook

**Files:**
- Create: `schema/seed_social_intel_accounts.sql` (template; user supplies the real handles at build time)
- Modify: `CLAUDE.md` (backfill-status + service-status rows)

**Interfaces:**
- Consumes: `social_intel.dim_accounts` (Task 1). This task is the ops/deploy step — gated on the user providing the initial watchlist handles.

- [ ] **Step 1: Confirm the initial watchlist with the user**

Ask the user for the initial watchlist: RM's own handles (one per platform per brand) + the competitor/peer set. Each row needs `(account_id slug, platform, handle, display_name, category, is_owned, station_code)`.

- [ ] **Step 2: Write the seed SQL**

Create `schema/seed_social_intel_accounts.sql` (idempotent; replace the example rows with the user's real handles):

```sql
-- schema/seed_social_intel_accounts.sql
-- Initial watchlist. Idempotent: ON CONFLICT (account_id) DO UPDATE.
-- account_id slug convention: '<platform-prefix>:<handle>' e.g. 'ig:hyfinmke'.

INSERT INTO social_intel.dim_accounts
    (account_id, platform, handle, display_name, category, is_owned, station_code)
VALUES
    -- OWNED (Radio Milwaukee) — replace with real handles:
    ('ig:hyfinmke',  'instagram', 'hyfinmke',  'HYFIN',  'peer_station', true,  'HYFIN'),
    ('ig:radiomke',  'instagram', '88nineradiomilwaukee', '88Nine', 'peer_station', true, 'RM88'),
    -- COMPETITORS / peers — replace with the user-provided set:
    ('ig:competitor','instagram', 'competitor','Competitor', 'local_media', false, NULL)
ON CONFLICT (account_id) DO UPDATE SET
    platform     = EXCLUDED.platform,
    handle       = EXCLUDED.handle,
    display_name = EXCLUDED.display_name,
    category     = EXCLUDED.category,
    is_owned     = EXCLUDED.is_owned,
    station_code = EXCLUDED.station_code,
    active       = true;
```

- [ ] **Step 3: Apply the seed + smoke-test one real fetch**

```bash
source .venv/bin/activate
psql "$DATABASE_URL" -f schema/seed_social_intel_accounts.sql
# Smoke test one owned account end-to-end (writes a snapshot + posts + tags):
python loaders/load_socialfetch.py ig:hyfinmke instagram hyfinmke
```
Expected: stats dict with `skipped: false`, `posts_upserted > 0`, `enriched >= 0`. Verify in Neon: `SELECT count(*) FROM social_intel.fact_posts;` is non-zero.

- [ ] **Step 4: Set the Fly secret + schedule the weekly machine**

```bash
# Reuse the key already in ~/.radio-milwaukee/.env:
SF_KEY=$(grep -E '^SOCIALFETCH_API_KEY=' ~/.radio-milwaukee/.env | cut -d= -f2-)
flyctl secrets set --app rm-data-loader SOCIALFETCH_API_KEY="$SF_KEY"
flyctl deploy --app rm-data-loader
# Weekly scheduled machine (mirrors mailchimp-content-nightly):
flyctl machine run . --app rm-data-loader --schedule weekly \
  --name social-intel-weekly \
  --entrypoint "python jobs/refresh_social_intel.py"
```
Expected: secret set, deploy succeeds, machine `social-intel-weekly` listed in `flyctl machine list --app rm-data-loader`.

- [ ] **Step 5: Update CLAUDE.md status**

In `CLAUDE.md`, add to the "Other sources" backfill table:

```markdown
| Social intelligence (socialfetch) | [x] | socialfetch REST + Haiku | `social_intel.*`; weekly watchlist (owned + competitors); engagement-rate benchmark; assistant reads via query_sql |
```

And add to "Service status":

```markdown
- [x] **Social-intel weekly job** — Fly scheduled machine `social-intel-weekly` (`python jobs/refresh_social_intel.py`); `SOCIALFETCH_API_KEY` Fly secret set. `social_intel` granted to rm_readonly + in catalog/ask-sql allowlists + system prompt.
```

- [ ] **Step 6: Commit**

```bash
git add schema/seed_social_intel_accounts.sql CLAUDE.md
git commit -m "feat(social-intel): seed watchlist + deploy runbook + status"
```

---

## Final verification

- [ ] **Run the whole suite**

Run: `source .venv/bin/activate && python -m pytest -q`
Expected: all green (the `_db_available`/`_dsn` skipifs SKIP cleanly where Neon isn't reachable).

- [ ] **Confirm the assistant can reach it** (prod, after deploy)

Run: `curl -s -X POST https://data.radiomilwaukee.org/... ` is not the path — instead verify via the gated Fly endpoint with the internal token, OR ask the assistant in the dashboard: *"How does our Instagram engagement rate compare to the competitors we track, and what content themes are working best for them?"* Expect it to `get_schema` → `query_sql` against `social_intel.*`, lead with engagement rate, split owned vs competitor, and cite content tags.

---

## Self-review notes (author)

- **Spec coverage:** schema (Task 1), socialfetch client + envelope handling + normalize (Task 2), Haiku taxonomy (Task 3), idempotent loader (Task 4), weekly job with isolation + credit-abort + Slack (Task 5), grant + catalog/ask-sql allowlist + notes + dimension enumeration (Task 6), system prompt (Task 7), seed watchlist + Fly secret + scheduled machine + status (Task 8), tests throughout (per-task). PII stance (aggregate counts only) is enforced in the schema (no commenter columns) and the catalog (`caption`/`handle`/`display_name` blocked from enumeration via existing `_SENSITIVE_NAME_BITS`).
- **Build-time unknowns isolated:** exact socialfetch routes/field names are confirmed in Task 2 Step 1 (capture real fixture + read /openapi.json) and absorbed by the tolerant `_first()` candidate lists — not guessed inline. Initial watchlist handles are gathered in Task 8 Step 1.
- **Out of scope (fast-follows, separate specs):** curated `get_social_benchmark`/`get_social_content_insights` tools, ad-hoc live "research any account" tool, Reddit story radar, Social dashboard-tab cards.
