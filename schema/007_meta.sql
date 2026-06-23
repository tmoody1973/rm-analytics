-- 007_meta.sql — Meta (Facebook + Instagram) source tables.
--
-- TWO schemas on purpose (see CLAUDE.md):
--   meta_organic  <- Graph API / Page Insights (posts, pages, reels)
--   meta_ads      <- Marketing API / Ads Insights (spend, ROAS)
-- Different API shapes, permissions, and rate limits — kept apart so a change
-- to one never breaks the other. Cross-source joins happen in marts.
--
-- Join keys back to dim.brand_channels:
--   page_id       -> platform='fb_page'
--   ig_account_id -> platform='ig_profile'
--   ad_account_id -> platform='meta_ad_acct'
--
-- Populated by Coupler.io. loaded_at is audit only, never part of a PK.

-- ===========================================================================
-- ORGANIC  (Graph API)
-- ===========================================================================

-- Daily page/profile-level metrics. Grain: (date, page_id).
-- For Instagram, page_id holds the IG account id and platform distinguishes.
CREATE TABLE IF NOT EXISTS meta_organic.fact_page_daily (
    date            DATE        NOT NULL,
    page_id         TEXT        NOT NULL,
    platform        TEXT        NOT NULL DEFAULT 'fb',   -- 'fb' | 'ig'
    impressions     BIGINT      NOT NULL DEFAULT 0,
    reach           BIGINT      NOT NULL DEFAULT 0,
    engaged_users   BIGINT      NOT NULL DEFAULT 0,
    follows         BIGINT      NOT NULL DEFAULT 0,
    unfollows       BIGINT      NOT NULL DEFAULT 0,
    followers_total BIGINT      NOT NULL DEFAULT 0,
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date, page_id, platform)
);

-- Per-post lifetime stats. Grain: (post_id).
CREATE TABLE IF NOT EXISTS meta_organic.fact_post_lifetime (
    post_id         TEXT        NOT NULL,
    page_id         TEXT        NOT NULL,
    platform        TEXT        NOT NULL DEFAULT 'fb',   -- 'fb' | 'ig'
    impressions     BIGINT      NOT NULL DEFAULT 0,
    reach           BIGINT      NOT NULL DEFAULT 0,
    reactions       BIGINT      NOT NULL DEFAULT 0,
    comments        BIGINT      NOT NULL DEFAULT 0,
    shares          BIGINT      NOT NULL DEFAULT 0,
    video_views     BIGINT      NOT NULL DEFAULT 0,
    saves           BIGINT      NOT NULL DEFAULT 0,   -- IG
    profile_visits  BIGINT      NOT NULL DEFAULT 0,   -- IG
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (post_id)
);

-- Post metadata. Grain: (post_id).
CREATE TABLE IF NOT EXISTS meta_organic.dim_posts (
    post_id       TEXT        NOT NULL,
    page_id       TEXT        NOT NULL,
    platform      TEXT        NOT NULL DEFAULT 'fb',
    post_type     TEXT,                                -- photo|video|reel|carousel|status
    caption       TEXT,
    media_url     TEXT,
    permalink     TEXT,
    published_at  TIMESTAMPTZ,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (post_id)
);

-- ===========================================================================
-- PAID  (Marketing API)
-- ===========================================================================

-- Per-ad daily delivery + spend. Grain: (date, ad_id).
CREATE TABLE IF NOT EXISTS meta_ads.fact_ad_insights_daily (
    date          DATE        NOT NULL,
    ad_id         TEXT        NOT NULL,
    ad_account_id TEXT        NOT NULL,
    impressions   BIGINT      NOT NULL DEFAULT 0,
    reach         BIGINT      NOT NULL DEFAULT 0,
    clicks        BIGINT      NOT NULL DEFAULT 0,
    spend         NUMERIC     NOT NULL DEFAULT 0,
    cpm           NUMERIC     NOT NULL DEFAULT 0,
    cpc           NUMERIC     NOT NULL DEFAULT 0,
    conversions   BIGINT      NOT NULL DEFAULT 0,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date, ad_id)
);

-- Campaign -> ad_set hierarchy. Grain: (campaign_id).
CREATE TABLE IF NOT EXISTS meta_ads.dim_campaigns (
    campaign_id    TEXT        NOT NULL,
    ad_account_id  TEXT        NOT NULL,
    campaign_name  TEXT,
    objective      TEXT,
    status         TEXT,
    loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (campaign_id)
);

-- Ad creative metadata + hierarchy links. Grain: (ad_id).
CREATE TABLE IF NOT EXISTS meta_ads.dim_ads (
    ad_id         TEXT        NOT NULL,
    ad_set_id     TEXT,
    campaign_id   TEXT,
    ad_account_id TEXT        NOT NULL,
    ad_name       TEXT,
    creative_type TEXT,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (ad_id)
);

-- Indexes for dashboard query patterns.
CREATE INDEX IF NOT EXISTS ix_meta_org_page_date
    ON meta_organic.fact_page_daily (page_id, date);
CREATE INDEX IF NOT EXISTS ix_meta_org_post_page
    ON meta_organic.fact_post_lifetime (page_id);
CREATE INDEX IF NOT EXISTS ix_meta_ads_acct_date
    ON meta_ads.fact_ad_insights_daily (ad_account_id, date);
