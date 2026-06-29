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
