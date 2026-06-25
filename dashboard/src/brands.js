// Single source of truth for the brand model + the global brand/date filters.
// Decision (2026-06-25): the flagship "Radio Milwaukee" is ONE brand that merges
// station_code RM88 (broadcast/streaming/Nielsen/email) and RMORG (web/FB/IG/app).
// HYFIN, 414 Music, Rhythm Lab, and Grace Weber's Music Lab stay separate.

export const ALL = 'ALL'

// Brand keys + display labels + which warehouse channels each brand actually has.
// `channels` drives the "not measured for this brand" empty state — coverage is lopsided.
export const BRANDS = [
  { key: ALL, label: 'All Brands', channels: null },
  { key: 'RM', label: 'Radio Milwaukee', channels: ['streaming', 'nielsen', 'web', 'fb', 'ig', 'email', 'donations'] },
  { key: 'HYFIN', label: 'HYFIN', channels: ['streaming', 'nielsen', 'web', 'fb', 'ig', 'email', 'donations'] },
  { key: 'RM414', label: '414 Music', channels: ['streaming'] },
  { key: 'RLR', label: 'Rhythm Lab', channels: ['streaming'] },
  { key: 'GWML', label: "Grace Weber's Music Lab", channels: ['fb', 'ig', 'email'] },
]

const LABEL = Object.fromEntries(BRANDS.map((b) => [b.key, b.label]))
export const brandLabel = (key) => LABEL[key] || key

// Friendly display label for a raw warehouse station_code (RM88 reads "Radio Milwaukee").
const STATION_LABEL = {
  RM88: 'Radio Milwaukee', RMORG: 'Radio Milwaukee', HYFIN: 'HYFIN',
  RM414: '414 Music', RLR: 'Rhythm Lab', GWML: "Grace Weber's Music Lab",
}
export const stationLabel = (code) => STATION_LABEL[code] || code

// Friendly label for a GA4 property name (maps via its brand).
export const propertyLabel = (name) => {
  const b = fromGaProperty(name)
  return b ? brandLabel(b) : name
}

export function brandHasChannel(brandKey, channel) {
  if (brandKey === ALL) return true
  const b = BRANDS.find((x) => x.key === brandKey)
  return !!(b && b.channels && b.channels.includes(channel))
}

// ---- discriminator -> brand mappers (verified 2026-06-25 against live distinct values) ----
const STATION_TO_BRAND = { RM88: 'RM', RMORG: 'RM', HYFIN: 'HYFIN', RM414: 'RM414', RLR: 'RLR', GWML: 'GWML' }
const GA_PROP_TO_BRAND = { 'https://www.radiomilwaukee.org - GA4': 'RM', HYFIN: 'HYFIN' }
const FB_ACCT_TO_BRAND = { 'Radio Milwaukee': 'RM', HYFIN: 'HYFIN', "Grace Weber's Music Lab": 'GWML' }
const IG_ACCT_TO_BRAND = { radiomilwaukee: 'RM', '88nine.mke': 'RM', 'hyfin.mke': 'HYFIN', gwmusiclab: 'GWML' }
const EMAIL_LIST_TO_BRAND = { 'Radio Milwaukee List': 'RM', 'HYFIN List': 'HYFIN', "Grace Weber's Music Lab": 'GWML' }

export const fromStation = (v) => STATION_TO_BRAND[v] || null
export const fromGaProperty = (v) => GA_PROP_TO_BRAND[v] || null
export const fromFbAccount = (v) => FB_ACCT_TO_BRAND[v] || null
export const fromIgAccount = (v) => IG_ACCT_TO_BRAND[v] || null
export const fromEmailList = (v) => EMAIL_LIST_TO_BRAND[v] || null

// Filter rows to the selected brand. `field` is the discriminator column, `mapper`
// turns its value into a brand key. ALL passes everything through.
export function filterByBrand(rows, brandKey, field, mapper) {
  if (!rows) return []
  if (brandKey === ALL) return rows
  return rows.filter((r) => mapper(r[field]) === brandKey)
}

// ---- date range ----
// Presets degrade gracefully across sources with very different cadences
// (Nielsen ~monthly surveys, finance 3 months loaded, streaming daily since 2024).
export const DATE_RANGES = [
  { key: '30d', label: '30 days', days: 30 },
  { key: '90d', label: '90 days', days: 90 },
  { key: '12m', label: '12 months', days: 365 },
  { key: 'ytd', label: 'Year to date', ytd: true },
  { key: 'all', label: 'All time', all: true },
]
export const DEFAULT_RANGE = '12m'
export const rangeLabel = (key) => (DATE_RANGES.find((r) => r.key === key) || {}).label || key

// Returns the cutoff Date for a range key, or null for "all time".
export function rangeCutoff(rangeKey, now = new Date()) {
  const r = DATE_RANGES.find((x) => x.key === rangeKey)
  if (!r || r.all) return null
  if (r.ytd) return new Date(now.getFullYear(), 0, 1)
  const d = new Date(now)
  d.setDate(d.getDate() - r.days)
  return d
}

// Filter time-series rows by a date column (string like "2026-04-01" / ISO). Rows
// with an unparseable/missing date are kept (better to show than silently drop).
export function filterByDate(rows, dateField, rangeKey, now = new Date()) {
  if (!rows) return []
  const cutoff = rangeCutoff(rangeKey, now)
  if (!cutoff) return rows
  return rows.filter((r) => {
    const raw = r[dateField]
    if (!raw) return true
    const t = new Date(raw)
    return isNaN(t) ? true : t >= cutoff
  })
}
