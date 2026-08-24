-- schema/025_self_healing_objects.sql
--
-- WHY THIS EXISTS
--
-- 2026-07-10, the dashboard went blank: "Couldn't load data: Failed to fetch".
-- Coupler does not UPDATE its staging tables — it DROPs and re-CREATEs them on
-- every import. `DROP TABLE ... CASCADE` takes every dependent object with it, so
-- both clean views (022/023's v_ig_profile_monthly and 024's v_app_daily) were
-- destroyed overnight. Three of the dashboard's 41 queries referenced them, threw,
-- and the endpoint 500'd. Proof: those staging tables hold the HIGHEST oids in the
-- database — they are new objects wearing old names.
--
-- The same import silently undid a security control. schema/016 runs
--   ALTER DEFAULT PRIVILEGES IN SCHEMA meta_organic GRANT SELECT ON TABLES TO rm_readonly
-- so Coupler's brand-new stg_ig_profile_monthly was auto-granted to the assistant —
-- re-exposing the dirty table that PR #25 deliberately revoked.
--
-- Both failures share one cause: our hygiene layer depends on objects Coupler owns
-- and destroys. This migration makes the database repair itself.
--
--   1. `admin.managed_view`  — the live definition of every view we own.
--   2. `admin.readonly_table`— the EXPLICIT allowlist of what rm_readonly may read.
--                              Deny by default: a table Coupler invents tomorrow is
--                              unreadable until someone adds it here.
--   3. `admin.rebuild_all()` — recreates every managed view, then applies the grant
--                              policy. Idempotent. Safe to run any time.
--   4. An event trigger that calls it the instant a table is created in a Coupler
--      schema. Self-healing, within Coupler's own transaction.
--
-- The trigger NEVER raises. If a rebuild fails (say Coupler changed a column name),
-- it warns and lets the import succeed; the hardened /api/dashboard then renders the
-- 38 cards that still work and names the 3 that don't. A broken view must not be able
-- to block the data pipeline.
--
-- TO CHANGE A VIEW: add a migration that calls admin.register_view(). Do not edit the
-- old migration — admin.managed_view is the live definition, the .sql files are history.

CREATE SCHEMA IF NOT EXISTS admin;
REVOKE ALL ON SCHEMA admin FROM PUBLIC;

-- ─────────────────────────────────────────────────────── 1. managed views ───

CREATE TABLE IF NOT EXISTS admin.managed_view (
    view_name   text PRIMARY KEY,          -- schema-qualified
    definition  text NOT NULL,             -- a complete CREATE OR REPLACE VIEW statement
    grant_to    text,                      -- role to GRANT SELECT to, or NULL
    registered_at timestamptz NOT NULL DEFAULT now()
);

-- Register a view AND create it, so the registry can never drift from reality.
CREATE OR REPLACE FUNCTION admin.register_view(p_name text, p_ddl text, p_grant_to text DEFAULT NULL)
RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
    EXECUTE p_ddl;
    IF p_grant_to IS NOT NULL THEN
        EXECUTE format('GRANT SELECT ON %s TO %I', p_name, p_grant_to);
    END IF;
    INSERT INTO admin.managed_view (view_name, definition, grant_to)
    VALUES (p_name, p_ddl, p_grant_to)
    ON CONFLICT (view_name) DO UPDATE
       SET definition = EXCLUDED.definition,
           grant_to   = EXCLUDED.grant_to,
           registered_at = now();
END
$fn$;

-- ──────────────────────────────────────── 2. explicit read-only allowlist ───

CREATE TABLE IF NOT EXISTS admin.readonly_table (
    schema_name text NOT NULL,
    table_name  text NOT NULL,
    PRIMARY KEY (schema_name, table_name)
);

-- Seed from what rm_readonly can read TODAY, minus the dirty staging table, so nothing
-- the assistant currently uses breaks when the blanket default privilege goes away.
INSERT INTO admin.readonly_table (schema_name, table_name)
SELECT DISTINCT table_schema, table_name
FROM information_schema.role_table_grants
WHERE grantee = 'rm_readonly'
  AND privilege_type = 'SELECT'
  AND NOT (table_schema = 'meta_organic' AND table_name = 'stg_ig_profile_monthly')
ON CONFLICT DO NOTHING;

-- ──────────────────────────────── 3. the repair, idempotent and reentrant ───

CREATE OR REPLACE FUNCTION admin.rebuild_all() RETURNS void LANGUAGE plpgsql AS $fn$
DECLARE
    v record;
    t record;
BEGIN
    -- Views first: a grant on a view that doesn't exist yet would fail.
    FOR v IN SELECT view_name, definition, grant_to FROM admin.managed_view ORDER BY view_name LOOP
        BEGIN
            EXECUTE v.definition;
            IF v.grant_to IS NOT NULL THEN
                EXECUTE format('GRANT SELECT ON %s TO %I', v.view_name, v.grant_to);
            END IF;
        EXCEPTION WHEN OTHERS THEN
            -- A view whose source table changed shape must not abort Coupler's import.
            RAISE WARNING 'admin.rebuild_all: could not rebuild % — %', v.view_name, SQLERRM;
        END;
    END LOOP;

    -- Then the grant policy. Deny by default: anything not on the allowlist stays unreadable.
    FOR t IN
        SELECT r.schema_name, r.table_name
        FROM admin.readonly_table r
        JOIN information_schema.tables i
          ON i.table_schema = r.schema_name AND i.table_name = r.table_name
    LOOP
        BEGIN
            EXECUTE format('GRANT SELECT ON %I.%I TO rm_readonly', t.schema_name, t.table_name);
        EXCEPTION WHEN OTHERS THEN
            RAISE WARNING 'admin.rebuild_all: could not grant %.% — %', t.schema_name, t.table_name, SQLERRM;
        END;
    END LOOP;

    -- Belt and braces: the dirty table is off the allowlist, but revoke explicitly in
    -- case a default privilege is ever re-added. This is the control PR #25 relied on.
    BEGIN
        REVOKE SELECT ON meta_organic.stg_ig_profile_monthly FROM rm_readonly;
    EXCEPTION WHEN OTHERS THEN
        NULL;   -- table absent mid-import; the next call catches it
    END;
END
$fn$;

-- ───────────────────────────────────────────── 4. fire when Coupler rebuilds ───

CREATE OR REPLACE FUNCTION admin.on_table_created() RETURNS event_trigger LANGUAGE plpgsql AS $fn$
DECLARE
    cmd record;
BEGIN
    FOR cmd IN SELECT * FROM pg_event_trigger_ddl_commands() LOOP
        -- Only CREATE TABLE, and only in the schemas Coupler rewrites. Filtering on the
        -- command tag also stops infinite recursion: rebuild_all() issues CREATE VIEW and
        -- GRANT, which re-enter this trigger and fall straight through.
        IF cmd.command_tag IN ('CREATE TABLE', 'SELECT INTO')
           AND split_part(cmd.object_identity, '.', 1) IN ('meta_organic', 'ga', 'email_esp', 'meta_ads')
        THEN
            PERFORM admin.rebuild_all();
            RETURN;   -- one rebuild per statement is enough
        END IF;
    END LOOP;
END
$fn$;

DROP EVENT TRIGGER IF EXISTS trg_rebuild_on_table_created;
CREATE EVENT TRIGGER trg_rebuild_on_table_created
    ON ddl_command_end
    EXECUTE FUNCTION admin.on_table_created();

-- ────────────────── 5. register the views we own, from their LIVE definitions ───

-- Read the definition out of the catalog rather than re-pasting the SQL here: the
-- registry cannot drift from what 023/024 actually created, and the reasoning stays
-- in those files where it belongs. Requires the views to exist (they do; 023/024 run
-- before this migration).
SELECT admin.register_view(
    'meta_organic.v_ig_profile_monthly',
    'CREATE OR REPLACE VIEW meta_organic.v_ig_profile_monthly AS '
        || pg_get_viewdef('meta_organic.v_ig_profile_monthly'::regclass),
    'rm_readonly');

SELECT admin.register_view(
    'ga.v_app_daily',
    'CREATE OR REPLACE VIEW ga.v_app_daily AS '
        || pg_get_viewdef('ga.v_app_daily'::regclass),
    'rm_readonly');

-- ─────────────────────────── 6. retire the blanket auto-grant (the security bug) ───

-- schema/016 granted SELECT on every FUTURE table in these schemas. That is what
-- re-exposed the dirty Instagram staging table when Coupler recreated it. The
-- allowlist above replaces it: new tables are unreadable until someone says otherwise.
ALTER DEFAULT PRIVILEGES IN SCHEMA meta_organic REVOKE SELECT ON TABLES FROM rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA ga           REVOKE SELECT ON TABLES FROM rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA meta_ads     REVOKE SELECT ON TABLES FROM rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA email_esp    REVOKE SELECT ON TABLES FROM rm_readonly;
-- wms / nielsen / finance / dim / marts are ours, not Coupler's: nothing drops and
-- recreates them, so their default privileges stay as schema/016 set them.
