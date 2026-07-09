import React from 'react'

// Radio Milwaukee brand palette (for Recharts — orange = highlight only, blue = data)
export const RM = {
  charcoal: '#1F2528', orange: '#F8971D', cream: '#F7F1DB', cream60: '#FAF6E6',
  blue: '#32588E', charcoal70: '#3A4146', blueSoft: '#8FA6C5', red: '#E03A2F',
  border: 'rgba(31,37,40,0.12)',
}
export const SERIES = [RM.charcoal, RM.blue, RM.orange, RM.blueSoft, RM.charcoal70]

// Brand colors, keyed by both the warehouse station_code and the display names the
// assistant uses when it labels a chart series, so a chart drawn in the chat agrees
// with the dashboard on what color HYFIN is.
// ponytail: tabs.jsx keeps its own 2-brand `stationColor`; folding it in here would
// change RLR from charcoal to blueSoft on the streaming tabs. Do that deliberately.
const BRAND_COLOR = {
  rm88: RM.orange, '88nine': RM.orange, '88nine radio milwaukee': RM.orange, 'radio milwaukee': RM.orange,
  hyfin: RM.blue,
  rm414: RM.charcoal70, '414 music': RM.charcoal70,
  rlr: RM.blueSoft, 'rhythm lab radio': RM.blueSoft,
}

/** Brand color for a station code or display label; null when the label isn't a brand. */
export const brandColor = (label) =>
  (typeof label === 'string' ? BRAND_COLOR[label.trim().toLowerCase()] : null) ?? null

/** Brand color when the series names a brand, else the next color in the palette. */
export const seriesColor = (label, i) => brandColor(label) ?? SERIES[i % SERIES.length]

export const money = (n) => (n == null ? '—' : '$' + Math.round(Number(n)).toLocaleString())
export const moneyK = (n) => (n == null ? '—' : '$' + Math.round(Number(n) / 1000).toLocaleString() + 'K')
export const num = (n) => (n == null ? '—' : Math.round(Number(n)).toLocaleString())
export const pct = (n) => (n == null ? '—' : (Number(n) <= 1 ? (Number(n) * 100).toFixed(1) : Number(n).toFixed(1)) + '%')

// Shared Recharts props for the brand look
export const AXIS = { stroke: RM.charcoal70, fontSize: 12, tickLine: false }
export const GRID = { stroke: RM.border, strokeDasharray: '0' }
export const TOOLTIP = {
  contentStyle: { background: RM.charcoal, border: 'none', borderRadius: 8, color: RM.cream, fontSize: 12 },
  labelStyle: { color: RM.cream60 }, itemStyle: { color: RM.cream },
}

// Small accessible info tooltip — CSS-only popover, no dependency.
function InfoDot({ text }) {
  return (
    <span className="info-dot" tabIndex={0} role="img" aria-label={text}>
      ⓘ<span className="info-pop">{text}</span>
    </span>
  )
}

export function Kpi({ label, value, note, accent, info }) {
  return (
    <div className="card kpi">
      <div className="label">
        {label}
        {info ? <InfoDot text={info} /> : null}
      </div>
      <div className={'value' + (accent ? ' accent' : '')}>{value}</div>
      {note && <div className="note">{note}</div>}
    </div>
  )
}

export function HeaderKpi({ label, value, note }) {
  return (
    <div className="hkpi">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {note && <div className="note">{note}</div>}
    </div>
  )
}

export function ChartCard({ title, children, className = '', deck, info }) {
  return (
    <div className={'card chart-card ' + className}>
      <div className="card-head">
        <h3>{title}{info ? <InfoDot text={info} /> : null}</h3>
        {deck ? <p className="deck">{deck}</p> : null}
      </div>
      {children}
    </div>
  )
}

export function SectionTitle({ children }) {
  return <h2 className="section-title">{children}</h2>
}

// pivot rows like [{station_code, month, value}] into recharts-friendly [{month, RM88, HYFIN,...}]
export function pivot(rows, keyField, seriesField, valueField) {
  const out = {}
  for (const r of rows) {
    const k = r[keyField]
    out[k] = out[k] || { [keyField]: k }
    out[k][r[seriesField]] = Number(r[valueField])
  }
  return Object.values(out)
}
export function distinct(rows, field) {
  return [...new Set(rows.map((r) => r[field]))]
}

// Collapse rows to one per `key`, summing `val`. Used to re-aggregate after a brand
// filter narrows multi-station rows (e.g. device split, follower totals per date).
export function sumBy(rows, key, val) {
  const m = {}
  for (const r of rows) m[r[key]] = (m[r[key]] || 0) + Number(r[val] || 0)
  return Object.entries(m).map(([k, v]) => ({ [key]: k, [val]: v })).sort((a, b) => b[val] - a[val])
}

// HourGrid — 7 × 24 heatmap. rows have {dow 0=Sun..6=Sat, hour 0-23, aas}.
// Colors cells from cream → orange by aas relative to max. No external dependencies.
const DOW_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
export function HourGrid({ rows }) {
  if (!rows || !rows.length) {
    return <div style={{ color: RM.charcoal70, fontSize: 13, padding: '16px 0' }}>No hourly data for this selection.</div>
  }
  // Build lookup: grid[dow][hour] = sum of aas across all stations (ALL-mode)
  const grid = Array.from({ length: 7 }, () => new Array(24).fill(0))
  for (const r of rows) {
    const d = Number(r.dow), h = Number(r.hour), v = Number(r.aas || 0)
    if (d >= 0 && d < 7 && h >= 0 && h < 24) {
      grid[d][h] += v
    }
  }
  // Compute max after all stations have been accumulated
  let maxAas = 0
  for (let d = 0; d < 7; d++) {
    for (let h = 0; h < 24; h++) {
      if (grid[d][h] > maxAas) maxAas = grid[d][h]
    }
  }
  const cellW = 28, cellH = 22, rowLabelW = 36
  const totalW = rowLabelW + 24 * cellW
  // lerp cream → orange by intensity
  const lerp = (a, b, t) => Math.round(a + (b - a) * t)
  const cellColor = (v) => {
    if (!maxAas) return RM.cream
    const t = v / maxAas
    const r = lerp(0xF7, 0xF8, t), g = lerp(0xF1, 0x97, t), bl = lerp(0xDB, 0x1D, t)
    return `rgb(${r},${g},${bl})`
  }
  const hourLabels = Array.from({ length: 24 }, (_, i) => (i % 3 === 0 ? `${i}h` : ''))
  return (
    <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
      <div style={{ minWidth: totalW, fontFamily: 'inherit' }}>
        {/* Hour header */}
        <div style={{ display: 'flex', marginLeft: rowLabelW }}>
          {hourLabels.map((lbl, h) => (
            <div key={h} style={{ width: cellW, fontSize: 10, color: RM.charcoal70, textAlign: 'center', lineHeight: '18px' }}>
              {lbl}
            </div>
          ))}
        </div>
        {/* Rows */}
        {DOW_LABELS.map((dow, d) => (
          <div key={d} style={{ display: 'flex', alignItems: 'center', marginBottom: 2 }}>
            <div style={{ width: rowLabelW, fontSize: 11, color: RM.charcoal70, flexShrink: 0 }}>{dow}</div>
            {grid[d].map((v, h) => (
              <div
                key={h}
                title={`${dow} ${h}:00 — AAS ${v.toFixed(1)}`}
                style={{
                  width: cellW - 2, height: cellH, marginRight: 2,
                  background: cellColor(v),
                  borderRadius: 3,
                  flexShrink: 0,
                }}
              />
            ))}
          </div>
        ))}
        {/* Legend */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
          <span style={{ fontSize: 11, color: RM.charcoal70 }}>Low</span>
          <div style={{ display: 'flex', gap: 2 }}>
            {[0, 0.25, 0.5, 0.75, 1].map((t) => (
              <div key={t} style={{ width: 18, height: 12, background: cellColor(t * maxAas), borderRadius: 2 }} />
            ))}
          </div>
          <span style={{ fontSize: 11, color: RM.charcoal70 }}>High · max {maxAas.toFixed(1)} AAS</span>
        </div>
      </div>
    </div>
  )
}
