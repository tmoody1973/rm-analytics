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
    fetched_at      timestamptz NOT NULL DEFAULT now(),  -- NOT in upsert update set; reflects first-fetched time, not last-fetched.
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
