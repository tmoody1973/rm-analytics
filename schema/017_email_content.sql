-- schema/017_email_content.sql
-- Newsletter body content + LLM-derived topic tags for the assistant.
-- Raw Mailchimp content (fact_campaign_content) is vendor data; the derived
-- tags (fact_campaign_enrichment) are kept in a SEPARATE table so derived data
-- is never confused with what Mailchimp sent. Both key on campaign_id, aligned
-- with email_esp.fact_campaign_sends.

CREATE TABLE IF NOT EXISTS email_esp.fact_campaign_content (
    campaign_id  text PRIMARY KEY,
    plain_text   text,
    html         text,
    links        jsonb NOT NULL DEFAULT '[]'::jsonb,
    word_count   integer NOT NULL DEFAULT 0,
    fetched_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS email_esp.fact_campaign_enrichment (
    campaign_id      text PRIMARY KEY,
    primary_theme    text,
    topics           jsonb NOT NULL DEFAULT '[]'::jsonb,
    content_type     text,
    featured_artists jsonb NOT NULL DEFAULT '[]'::jsonb,
    enriched_at      timestamptz NOT NULL DEFAULT now(),
    model            text
);

-- rm_readonly already holds SELECT on the email_esp schema (schema/016), but
-- default privileges only cover pre-existing tables. Grant explicitly so the
-- assistant can read the new tables immediately.
GRANT SELECT ON email_esp.fact_campaign_content    TO rm_readonly;
GRANT SELECT ON email_esp.fact_campaign_enrichment TO rm_readonly;
