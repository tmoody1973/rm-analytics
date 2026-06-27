-- 018_funraise_readonly_grant.sql — funraise-unblock (MOO-177 follow-up)
-- Grant the assistant's read-only role SELECT on the funraise (donor) schema.
--
-- This INVERTS the deliberate omission in schema/016. It is safe ONLY because
-- the funraise data is DE-IDENTIFIED (no names, no raw email, no phone — see
-- funraise.dim_supporters) AND the tool endpoints that reach it are gated behind
-- INTERNAL_API_TOKEN (service/internal_auth.py). Do not apply this migration
-- without that gate live, or donor rows become reachable via the public
-- /api/ask-sql endpoint.
--
-- rm_readonly stays hard read-only (default_transaction_read_only, 15s timeout
-- from 016). This only adds SELECT visibility.

-- USAGE on the schema + SELECT on existing tables.
GRANT USAGE  ON SCHEMA funraise                TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA funraise  TO rm_readonly;

-- Future tables in funraise are also SELECT-able by the role.
ALTER DEFAULT PRIVILEGES IN SCHEMA funraise GRANT SELECT ON TABLES TO rm_readonly;
