import React from 'react'
import { BRANDS, DATE_RANGES, brandLabel } from './brands.js'

// Global filter bar: Brand + Period. Sits under the tabs, sticky.
export function FilterBar({ brand, range, onBrand, onRange }) {
  return (
    <div className="filterbar">
      <div className="filter">
        <label htmlFor="brand-select">Brand</label>
        <select id="brand-select" value={brand} onChange={(e) => onBrand(e.target.value)}>
          {BRANDS.map((b) => <option key={b.key} value={b.key}>{b.label}</option>)}
        </select>
      </div>
      <div className="filter">
        <label htmlFor="range-select">Period</label>
        <select id="range-select" value={range} onChange={(e) => onRange(e.target.value)}>
          {DATE_RANGES.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
        </select>
      </div>
    </div>
  )
}

// Chip shown on a widget that is not brand-attributable (finance, combined totals).
export function OrgWideBadge() {
  return <span className="badge org-wide" title="Organization-wide — not split by brand">Org-wide</span>
}

// Chip echoing the active brand context on a brand-attributable widget.
export function BrandBadge({ brand }) {
  if (!brand || brand === 'ALL') return null
  return <span className="badge brand">{brandLabel(brand)}</span>
}

// Empty state when the selected brand has no data for this channel.
export function NoBrandData({ brand, channel }) {
  return (
    <div className="no-brand-data">
      <div className="nbd-title">Not measured for {brandLabel(brand)}</div>
      <div className="nbd-sub">We don't have {channel} data for this brand{channel === 'nielsen' ? ' (Nielsen measures Radio Milwaukee and HYFIN only)' : ''}.</div>
    </div>
  )
}
