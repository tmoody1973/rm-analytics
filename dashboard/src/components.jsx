import React from 'react'

// Radio Milwaukee brand palette (for Recharts — orange = highlight only, blue = data)
export const RM = {
  charcoal: '#1F2528', orange: '#F8971D', cream: '#F7F1DB', cream60: '#FAF6E6',
  blue: '#32588E', charcoal70: '#3A4146', blueSoft: '#8FA6C5', red: '#E03A2F',
  border: 'rgba(31,37,40,0.12)',
}
export const SERIES = [RM.charcoal, RM.blue, RM.orange, RM.blueSoft, RM.charcoal70]

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

export function Kpi({ label, value, note, accent }) {
  return (
    <div className="card kpi">
      <div className="label">{label}</div>
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

export function ChartCard({ title, children, className = '' }) {
  return (
    <div className={'card chart-card ' + className}>
      <h3>{title}</h3>
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
