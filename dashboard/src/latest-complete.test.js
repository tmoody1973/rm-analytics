import { describe, it, expect } from 'vitest'
import { latestCompletePeriod } from './components.jsx'

// The bug this guards: the Social tab summed the latest month where ANY account had a
// value. HYFIN's 2026-07 engagement is NULL (the view's impossible-value guard), so the
// org-wide tile summed 3 of 4 accounts — 10,611 — and presented it as the total. The last
// month all four reported, 2026-06, totals 25,673. A 59% understatement, labelled "Latest
// month". Never sum a partial period and call it a total.

const rows = [
  { month: '2026-05', account: 'a', v: 10 },
  { month: '2026-05', account: 'b', v: 20 },
  { month: '2026-06', account: 'a', v: 30 },
  { month: '2026-06', account: 'b', v: 40 },
  { month: '2026-07', account: 'a', v: 50 },
  { month: '2026-07', account: 'b', v: null },   // guard nulled this one
]
const call = (rs) => latestCompletePeriod(rs, 'v', 'month', 'account')

describe('latestCompletePeriod', () => {
  it('prefers the latest period where every reporting entity has a value', () => {
    expect(call(rows)).toEqual({ value: 70, period: '2026-06', covered: 2, expected: 2 })
  })

  it('does NOT sum the fresher partial period', () => {
    expect(call(rows).value).not.toBe(50)
  })

  it('returns null when nothing was ever measured', () => {
    expect(call([{ month: '2026-07', account: 'a', v: null }])).toBeNull()
  })

  it('ignores an entity that never reports the metric when sizing coverage', () => {
    // 'c' never reports v, so it must not block 2026-07 from counting as complete.
    const withGhost = [
      { month: '2026-07', account: 'a', v: 5 },
      { month: '2026-07', account: 'b', v: 7 },
      { month: '2026-07', account: 'c', v: null },
    ]
    expect(call(withGhost)).toEqual({ value: 12, period: '2026-07', covered: 2, expected: 2 })
  })

  it('falls back to the latest partial period when no period is ever complete', () => {
    const neverFull = [
      { month: '2026-06', account: 'a', v: 1 },
      { month: '2026-06', account: 'b', v: null },
      { month: '2026-07', account: 'a', v: null },
      { month: '2026-07', account: 'b', v: 9 },
    ]
    // Both accounts report v at some point, but never in the same month.
    expect(call(neverFull)).toEqual({ value: 9, period: '2026-07', covered: 1, expected: 2 })
  })

  it('a single-entity filter is complete as soon as that entity reports', () => {
    const solo = rows.filter((r) => r.account === 'a')
    expect(call(solo)).toEqual({ value: 50, period: '2026-07', covered: 1, expected: 1 })
  })

  it('treats a genuine zero as measured', () => {
    const zeroed = [{ month: '2026-07', account: 'a', v: 0 }, { month: '2026-07', account: 'b', v: 4 }]
    expect(call(zeroed)).toEqual({ value: 4, period: '2026-07', covered: 2, expected: 2 })
  })
})
