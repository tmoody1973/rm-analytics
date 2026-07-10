-- schema/023_ig_profile_clean_v2.sql
-- Revises meta_organic.v_ig_profile_monthly (schema/022) on two counts.
--
-- 1. THE GUARD BLAMED THE WRONG COLUMN.
--    022 nulled `engagements` whenever `engagements > reach`, assuming reach was
--    trustworthy. It isn't always. Exactly two rows in the table are impossible,
--    and they fail for opposite reasons:
--
--      account     month     reach   engagements  accounts_engaged
--      hyfin.mke   2026-02    9,399      37,624             1,695   <- engagements bad (shares = 17,134, ~70x)
--      hyfin.mke   2026-07    2,213       7,327             6,135   <- REACH bad
--
--    `accounts_engaged` is the discriminator: you cannot engage with a post you
--    were never shown, so accounts_engaged > reach can ONLY mean reach is wrong.
--    022 never checked it, so it silently kept a broken reach (2,213) and threw
--    away a real engagement number (7,327).
--
-- 2. THE IN-PROGRESS MONTH LOOKED COMPLETE.
--    Coupler re-pulls the current month every night, so its row covers only the
--    days elapsed — 2026-07-01..2026-07-09 when this was written. Presented next
--    to 30-day months it reads as collapse. Consumers need to know.
--
--    NOTE: Coupler caps its window at 30 days, so a 31-day month legitimately
--    ends on the 30th. `is_complete` is therefore window-based, not a calendar
--    comparison — and deliberately NOT clock-based (`month = current month`),
--    so a stalled Coupler can't leave a 9-day stub looking finished forever.
--
-- Staging stays untouched (Coupler re-imports it); the hygiene lives here.
-- CREATE OR REPLACE keeps the existing grants and the rm_readonly REVOKE from 022;
-- new columns are appended, existing ones keep their position and type.

CREATE OR REPLACE VIEW meta_organic.v_ig_profile_monthly AS
WITH clean AS (
    -- ponytail: one rule, `x <= 0 -> NULL`, kills the -1 sentinels AND both
    -- collection gaps without hardcoding cutoff dates. A true zero month for an
    -- active brand account doesn't happen; a gap does. GREATEST(NULL,0)=0 in
    -- Postgres, so NULL stays NULL.
    SELECT
        account__account_name                                  AS account,
        report__start_date                                     AS month,
        report__end_date                                       AS period_end,
        NULLIF(GREATEST(performance__reach, 0), 0)             AS reach_raw,
        NULLIF(GREATEST(performance__engagements, 0), 0)       AS engagements_raw,
        NULLIF(GREATEST(engagement__views, 0), 0)              AS views,
        NULLIF(GREATEST(engagement__accounts_engaged, 0), 0)   AS accounts_engaged_raw,
        NULLIF(GREATEST(engagement__likes, 0), 0)              AS likes,
        NULLIF(GREATEST(engagement__comments, 0), 0)           AS comments,
        NULLIF(GREATEST(engagement__shares, 0), 0)             AS shares,
        NULLIF(GREATEST(engagement__saves, 0), 0)              AS saves,
        NULLIF(GREATEST(engagement__replies, 0), 0)            AS replies,
        NULLIF(GREATEST(clicks__website_clicks, 0), 0)         AS website_clicks,
        NULLIF(GREATEST(clicks__profile_links_clicks, 0), 0)   AS profile_links_clicks
    FROM meta_organic.stg_ig_profile_monthly
),
guarded AS (
    -- Decide WHICH metric is wrong before nulling anything. accounts_engaged > reach is
    -- physically impossible and implicates reach itself. engagements > reach with
    -- accounts_engaged sitting BELOW reach implicates the engagement components instead
    -- (Feb 2026: shares = 17,134). So reach loses only when accounts_engaged testifies
    -- against it — and accounts_engaged is the witness, never the accused.
    SELECT
        account, month, period_end, views, likes, comments, shares, saves, replies,
        website_clicks, profile_links_clicks,
        CASE WHEN accounts_engaged_raw > reach_raw
             THEN NULL ELSE reach_raw END AS reach,
        -- COALESCE(..., TRUE): accounts_engaged is NULL before Dec 2025, so there is no
        -- witness. Fall back to 022's rule and blame engagements. Without it the AND goes
        -- NULL and an impossible row would leak through kept.
        CASE WHEN engagements_raw > reach_raw
                  AND COALESCE(accounts_engaged_raw <= reach_raw, TRUE)
             THEN NULL ELSE engagements_raw END AS engagements,
        accounts_engaged_raw AS accounts_engaged
    FROM clean
)
SELECT account, month, reach, engagements, views, accounts_engaged,
       likes, comments, shares, saves, replies,
       website_clicks, profile_links_clicks,
       round(engagements::numeric / NULLIF(reach, 0), 4) AS engagement_rate,
       period_end,
       -- The reporting window ran to the end of the month, or to Coupler's 30-day
       -- cap, whichever comes first. Anything short of that is still accumulating.
       (period_end >= LEAST((month + interval '1 month - 1 day')::date, month + 29)) AS is_complete
FROM guarded;

COMMENT ON VIEW meta_organic.v_ig_profile_monthly IS
  'Clean IG monthly profile metrics. NULL means NOT MEASURED, never zero. '
  'is_complete = false for the month still in progress — do not compare it to full months.';

-- 022 already granted the view to rm_readonly and revoked the raw table.
-- CREATE OR REPLACE preserves both; re-stated here so a fresh database is correct.
GRANT SELECT ON meta_organic.v_ig_profile_monthly TO rm_readonly;
REVOKE SELECT ON meta_organic.stg_ig_profile_monthly FROM rm_readonly;
