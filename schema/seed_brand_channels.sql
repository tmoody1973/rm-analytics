-- seed_brand_channels.sql — channel mapping seed (idempotent, re-runnable).
--
-- Source of IDs: the legacy "Radio Milwaukee Dashboard Hub" Google Sheet
-- (inventoried 2026-06-23). Maps each GA4 property / FB page / IG profile /
-- Mailchimp list to a station_code so cross-source marts joins never need
-- hardcoded handle filters.
--
-- platform vocabulary: 'ga4' | 'fb_page' | 'ig_profile' | 'mailchimp_list'
--
-- GAPS to fill via the Coupler.io MCP (authoritative IDs) — intentionally NOT
-- seeded here to avoid wrong join keys:
--   * RM88 ig_profile '88nine.mke'  — numeric IG id was mangled to scientific
--     notation in the sheet (1.78415E+16); needs the real 17841… id.
--   * GWML fb_page 'gwmusiclab'      — sheet had only the handle, no numeric
--     page id.
--   * RM88 fb_page 'radiomilwaukee'  — confirm whether a separate FB page from
--     88Nine exists.
--   * Mailchimp list 922d1c5a06 ('Funraise') — donor-synced audience, not a
--     brand newsletter; decide mapping (likely org/RM88) later.

-- 1) GWML is its own brand (Grace Weber's Music Lab) — social + email only, no
--    stream. Add it before the channel rows (FK: brand_channels.station_code).
INSERT INTO dim.stations (code, brand_name, format, mount_point)
VALUES ('GWML', 'Grace Weber''s Music Lab', 'Artist Development / Music Program', NULL)
ON CONFLICT (code) DO NOTHING;

-- 2) Channel mappings (confident IDs only).
INSERT INTO dim.brand_channels (station_code, platform, handle_or_id, display_name)
VALUES
    -- GA4 properties (one per website)
    ('RM88',  'ga4',            '409066609',          'Radio Milwaukee website (GA4)'),
    ('HYFIN', 'ga4',            '304846646',          'HYFIN website (GA4)'),
    -- Facebook pages
    ('RM88',  'fb_page',        '104128795458344',    '88Nine Facebook'),
    ('HYFIN', 'fb_page',        '103278985544368',    'HYFIN Facebook'),
    -- Instagram profiles
    ('RM88',  'ig_profile',     '17841400938340002',  'radiomilwaukee IG'),
    ('HYFIN', 'ig_profile',     '17841452098910774',  'hyfin.mke IG'),
    ('GWML',  'ig_profile',     '17841406452677056',  'gwmusiclab IG'),
    -- Mailchimp lists
    ('RM88',  'mailchimp_list', 'd2583b1492',         'Radio Milwaukee List'),
    ('HYFIN', 'mailchimp_list', 'dbf0d7bdf6',         'HYFIN List'),
    ('GWML',  'mailchimp_list', 'c31a5fe86d',         'Grace Weber''s Music Lab List')
ON CONFLICT (platform, handle_or_id)
DO UPDATE SET station_code = EXCLUDED.station_code,
              display_name = EXCLUDED.display_name;
