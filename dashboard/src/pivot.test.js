import { describe, it, expect } from 'vitest'
import { pivot, toNumOrNull } from './components.jsx'

// `Number(null) === 0`. Before this guard, pivot silently turned every "not measured"
// month from meta_organic.v_ig_profile_monthly into a data point at zero — telling
// leadership HYFIN had zero engagement for seven months of 2025. Same defect class as
// PR #25, one layer up. Missing is a gap; zero is a claim.

describe('toNumOrNull', () => {
  it('maps null, undefined and empty string to null', () => {
    expect([toNumOrNull(null), toNumOrNull(undefined), toNumOrNull('')]).toEqual([null, null, null])
  })

  it('maps an unparseable value to null rather than NaN', () => {
    expect(toNumOrNull('n/a')).toBeNull()
  })

  it('preserves a real zero', () => {
    expect(toNumOrNull(0)).toBe(0)
  })

  it('coerces numeric strings from SQL', () => {
    expect(toNumOrNull('1234')).toBe(1234)
  })
})

describe('pivot', () => {
  const rows = [
    { month: '2025-07', account: 'hyfin.mke', engagements: null },
    { month: '2025-08', account: 'hyfin.mke', engagements: 925 },
    { month: '2025-08', account: '88nine.mke', engagements: '4200' },
    { month: '2026-02', account: 'hyfin.mke', engagements: null },
  ]

  const out = pivot(rows, 'month', 'account', 'engagements')

  it('leaves an unmeasured month null so Recharts draws a gap', () => {
    expect(out.find((r) => r.month === '2025-07')['hyfin.mke']).toBeNull()
  })

  it('leaves a mid-series unmeasured month null too', () => {
    expect(out.find((r) => r.month === '2026-02')['hyfin.mke']).toBeNull()
  })

  it('never yields 0 for a null input', () => {
    expect(out.flatMap((r) => Object.values(r))).not.toContain(0)
  })

  it('still pivots real values, coercing numeric strings', () => {
    const aug = out.find((r) => r.month === '2025-08')
    expect(aug).toEqual({ month: '2025-08', 'hyfin.mke': 925, '88nine.mke': 4200 })
  })

  it('keeps a genuine zero measurement', () => {
    const z = pivot([{ m: 'Jan', s: 'a', v: 0 }], 'm', 's', 'v')
    expect(z[0].a).toBe(0)
  })
})
