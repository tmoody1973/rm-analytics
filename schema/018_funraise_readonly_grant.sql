-- 018_funraise_readonly_grant.sql — funraise-unblock (MOO-177 follow-up)
-- Grant the assistant's read-only role SELECT on the funraise (donor) schema.
--
-- This INVERTS the deliberate omission in schema/016. It is safe ONLY because
-- the funraise data is DE-IDENTIFIED (no names, no raw email, no phone) AND the
-- tool endpoints that reach it are gated behind INTERNAL_API_TOKEN
-- (service/internal_auth.py). Do not apply this migration without that gate live,
-- or donor rows become reachable via the public /api/ask-sql endpoint.
--
-- COLUMN-LEVEL on dim_supporters: email_sha256 is a one-way email HASH — not a
-- readable address, but a stable join key that could re-identify a donor against
-- a known email list. So the role is granted SELECT on every dim_supporters
-- column EXCEPT email_sha256. (A table-level GRANT would expose it; column-level
-- makes the role itself the authoritative enforcer rather than the LLM prompt.)
--
-- No blanket "ALL TABLES" / ALTER DEFAULT PRIVILEGES grant here, on purpose: a
-- future funraise table must be granted explicitly so new donor PII is never
-- auto-exposed. rm_readonly stays hard read-only (set in 016).

GRANT USAGE ON SCHEMA funraise TO rm_readonly;

-- Non-PII tables: table-level SELECT is fine (no readable PII columns exist).
GRANT SELECT ON funraise.fact_transactions  TO rm_readonly;
GRANT SELECT ON funraise.fact_subscriptions TO rm_readonly;
GRANT SELECT ON funraise.dim_campaigns      TO rm_readonly;

-- dim_supporters: explicit columns, email_sha256 deliberately omitted.
GRANT SELECT (
    supporter_id,
    city, state, postal_code, country,
    first_donation_at, last_donation_at,
    lifetime_total, lifetime_recurring, lifetime_onetime,
    active_12mo, loaded_at
) ON funraise.dim_supporters TO rm_readonly;

-- Belt-and-suspenders: ensure the hash column is never readable by this role,
-- even if a prior table-level grant existed.
REVOKE SELECT (email_sha256) ON funraise.dim_supporters FROM rm_readonly;
