-- schema/seed_social_intel_accounts.sql
-- Initial Social Intelligence watchlist (24 accounts, Instagram, v1).
-- Researched + verified 2026-06-28 from official sites / live profiles.
-- account_id slug convention: 'ig:<handle>'. Idempotent: ON CONFLICT (account_id) DO UPDATE.
-- WKKV/V100.7 (HYFIN's top local urban-radio competitor) intentionally deferred —
-- handle unconfirmed; add later.

INSERT INTO social_intel.dim_accounts
    (account_id, platform, handle, display_name, category, is_owned, station_code)
VALUES
    -- ─── OWNED — Radio Milwaukee ───
    ('ig:radiomilwaukee', 'instagram', 'radiomilwaukee', '88Nine Radio Milwaukee', 'peer_station', true,  'RM88'),
    ('ig:hyfin.mke',      'instagram', 'hyfin.mke',      'HYFIN',                  'peer_station', true,  'HYFIN'),
    ('ig:rhythmlabradio', 'instagram', 'rhythmlabradio', 'Rhythm Lab Radio',       'peer_station', true,  'RLR'),

    -- ─── PEER STATIONS — public radio AAA + local ───
    ('ig:wmsemke',        'instagram', 'wmsemke',        'WMSE 91.7',              'peer_station', false, NULL),
    ('ig:kexp',           'instagram', 'kexp',           'KEXP',                   'peer_station', false, NULL),
    ('ig:thecurrent',     'instagram', 'thecurrent',     'The Current (MPR)',      'peer_station', false, NULL),
    ('ig:kcrw',           'instagram', 'kcrw',           'KCRW',                   'peer_station', false, NULL),
    ('ig:wxpnfm',         'instagram', 'wxpnfm',         'WXPN',                   'peer_station', false, NULL),
    ('ig:kutx',           'instagram', 'kutx',           'KUTX',                   'peer_station', false, NULL),
    ('ig:wnxpnashville',  'instagram', 'wnxpnashville',  'WNXP Nashville',         'peer_station', false, NULL),
    ('ig:wbgojazz',       'instagram', 'wbgojazz',       'WBGO',                   'peer_station', false, NULL),

    -- ─── LOCAL MEDIA — Milwaukee ───
    ('ig:milwaukeerecord',            'instagram', 'milwaukeerecord',            'Milwaukee Record',           'local_media', false, NULL),
    ('ig:shepherdexpress',            'instagram', 'shepherdexpress',            'Shepherd Express',           'local_media', false, NULL),
    ('ig:onmilwaukee',                'instagram', 'onmilwaukee',                'OnMilwaukee',                'local_media', false, NULL),
    ('ig:milwaukeemag',               'instagram', 'milwaukeemag',               'Milwaukee Magazine',         'local_media', false, NULL),
    ('ig:milwaukeecommunityjournal',  'instagram', 'milwaukeecommunityjournal',  'Milwaukee Community Journal','local_media', false, NULL),

    -- ─── MUSIC DISCOVERY BRANDS ───
    ('ig:nprmusic',       'instagram', 'nprmusic',       'NPR Music / Tiny Desk',  'music_brand', false, NULL),
    ('ig:audiotree',      'instagram', 'audiotree',      'Audiotree',              'music_brand', false, NULL),
    ('ig:nts_radio',      'instagram', 'nts_radio',      'NTS Radio',              'music_brand', false, NULL),
    ('ig:colorsxstudios', 'instagram', 'colorsxstudios', 'COLORS',                 'music_brand', false, NULL),

    -- ─── BLACK MEDIA — HYFIN benchmarks ───
    ('ig:okayplayer',     'instagram', 'okayplayer',     'Okayplayer',             'music_brand', false, NULL),
    ('ig:thefader',       'instagram', 'thefader',       'The FADER',              'music_brand', false, NULL),
    ('ig:revolt',         'instagram', 'revolt',         'REVOLT',                 'music_brand', false, NULL),
    ('ig:afropunk',       'instagram', 'afropunk',       'AfroPunk',               'music_brand', false, NULL),
    ('ig:afrotech',       'instagram', 'afrotech',       'AfroTech',               'music_brand', false, NULL),
    ('ig:blavityinc',     'instagram', 'blavityinc',     'Blavity',                'music_brand', false, NULL)
ON CONFLICT (account_id) DO UPDATE SET
    platform     = EXCLUDED.platform,
    handle       = EXCLUDED.handle,
    display_name = EXCLUDED.display_name,
    category     = EXCLUDED.category,
    is_owned     = EXCLUDED.is_owned,
    station_code = EXCLUDED.station_code,
    active       = true;
