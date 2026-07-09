-- schema/022_ig_profile_clean.sql
-- One clean view over the IG monthly staging table, because the raw Coupler data
-- has three defects that were being reported to leadership as fact:
--
--   1. COLLECTION GAP — every engagement metric is 0 for all four accounts before
--      2025-08 (reach IS populated, so it's a gap, not zero activity).
--      `accounts_engaged` has a second, later gap (0 until 2025-12).
--   2. SENTINELS — `-1` appears for engagements/saves (88nine.mke 2025-01,
--      hyfin.mke 2025-03/04). SUM/AVG silently absorb it.
--   3. IMPOSSIBLE VALUES — hyfin.mke 2026-02 reports 37,624 engagements against
--      9,399 reach (400%), driven by shares=17,134 (~70x its neighbours);
--      2026-07 is the same shape (331%). Engagements cannot exceed reach.
--
-- Both consumers (the dashboard's social_ig_monthly query, and the assistant via
-- query_sql) read the raw table today. Fixing one leaves the other lying, so the
-- guard lives here — and rm_readonly is REVOKED on the raw table so the assistant
-- cannot route around it. The dashboard connects as owner and is repointed to the
-- view; `combined_digital_reach` still sums raw `reach`, which is clean.
--
-- Staging is untouched (Coupler re-imports it); the hygiene is a view.

CREATE OR REPLACE VIEW meta_organic.v_ig_profile_monthly AS
WITH clean AS (
    -- ponytail: one rule, `x <= 0 -> NULL`, kills the -1 sentinels AND both
    -- collection gaps without hardcoding cutoff dates. A true zero month for an
    -- active brand account doesn't happen; a gap does. GREATEST(NULL,0)=0 in
    -- Postgres, so NULL stays NULL.
    SELECT
        account__account_name                                  AS account,
        report__start_date                                     AS month,
        NULLIF(GREATEST(performance__reach, 0), 0)             AS reach,
        NULLIF(GREATEST(performance__engagements, 0), 0)       AS engagements_raw,
        NULLIF(GREATEST(engagement__views, 0), 0)              AS views,
        NULLIF(GREATEST(engagement__accounts_engaged, 0), 0)   AS accounts_engaged,
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
    -- ponytail: engagements > reach is physically impossible. Empirically only
    -- hyfin.mke 2026-02 and 2026-07 trip this. Loosen the threshold if a legit
    -- multi-action month ever exceeds reach.
    SELECT *,
           CASE WHEN engagements_raw > reach THEN NULL ELSE engagements_raw END AS engagements
    FROM clean
)
SELECT account, month, reach, engagements, views, accounts_engaged,
       likes, comments, shares, saves, replies,
       website_clicks, profile_links_clicks,
       round(engagements::numeric / NULLIF(reach, 0), 4) AS engagement_rate
FROM guarded;

-- The assistant reads the clean view only.
GRANT SELECT ON meta_organic.v_ig_profile_monthly TO rm_readonly;
REVOKE SELECT ON meta_organic.stg_ig_profile_monthly FROM rm_readonly;
