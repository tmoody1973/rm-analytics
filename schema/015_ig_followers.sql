-- Instagram absolute follower count — daily snapshot.
-- The Coupler IG Insights monthly feed has NO absolute follower total (the
-- net follows/unfollows column is null), so we pull `followers_count` straight
-- from the Meta Graph API and store one row per (snapshot_date, ig_user_id).
-- Source schema stays sacred: brand mapping (handle -> station_code) is done in
-- the presentation/marts layer via the same map as dim.brand_channels.

CREATE TABLE IF NOT EXISTS meta_organic.fact_ig_followers_daily (
    snapshot_date   DATE        NOT NULL,
    ig_user_id      TEXT        NOT NULL,   -- numeric IG Business Account id
    account_name    TEXT,                   -- handle, e.g. 'radiomilwaukee'
    followers_count BIGINT,
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_date, ig_user_id)
);

COMMENT ON TABLE meta_organic.fact_ig_followers_daily IS
    'Daily Instagram follower totals pulled from the Meta Graph API (followers_count). One row per account per day. Idempotent on (snapshot_date, ig_user_id).';
