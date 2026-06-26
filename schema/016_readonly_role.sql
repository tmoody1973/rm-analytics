-- 016_readonly_role.sql — MOO-173 Phase 0b
-- Dedicated read-only role for the AI assistant's guarded SQL fallback.
-- SELECT only, on an allowlist of NON-PII schemas. The funraise (donor) schema
-- is deliberately omitted — donor data reaches the assistant only as metric
-- aggregates. This role is the AUTHORITATIVE safety boundary; the app-layer
-- validator in service/ask_sql_api.py is a second, fail-fast layer.
--
-- Password is set out-of-band (Neon MCP / console) and stored ONLY in the Fly
-- secret DATABASE_URL_RO and ~/.radio-milwaukee/.env — never in this file.

-- 1. Role (idempotent).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rm_readonly') THEN
    CREATE ROLE rm_readonly LOGIN;
  END IF;
END
$$;

-- 2. Hard read-only + finite timeout at the role level.
ALTER ROLE rm_readonly SET default_transaction_read_only = on;
ALTER ROLE rm_readonly SET statement_timeout = '15s';

-- 3. SELECT on each allowlisted schema (existing + future tables).
GRANT USAGE ON SCHEMA wms          TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA wms          TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA wms          GRANT SELECT ON TABLES TO rm_readonly;

GRANT USAGE ON SCHEMA nielsen      TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA nielsen      TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA nielsen      GRANT SELECT ON TABLES TO rm_readonly;

GRANT USAGE ON SCHEMA ga           TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA ga           TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA ga           GRANT SELECT ON TABLES TO rm_readonly;

GRANT USAGE ON SCHEMA meta_organic TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA meta_organic TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA meta_organic GRANT SELECT ON TABLES TO rm_readonly;

GRANT USAGE ON SCHEMA meta_ads     TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA meta_ads     TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA meta_ads     GRANT SELECT ON TABLES TO rm_readonly;

GRANT USAGE ON SCHEMA email_esp    TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA email_esp    TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA email_esp    GRANT SELECT ON TABLES TO rm_readonly;

GRANT USAGE ON SCHEMA finance      TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA finance      TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA finance      GRANT SELECT ON TABLES TO rm_readonly;

GRANT USAGE ON SCHEMA dim          TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA dim          TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA dim          GRANT SELECT ON TABLES TO rm_readonly;

GRANT USAGE ON SCHEMA marts        TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA marts        TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA marts        GRANT SELECT ON TABLES TO rm_readonly;

-- 4. Defensive: ensure no funraise (donor) access, even if ever granted.
REVOKE ALL ON ALL TABLES IN SCHEMA funraise FROM rm_readonly;
REVOKE ALL ON SCHEMA funraise FROM rm_readonly;
