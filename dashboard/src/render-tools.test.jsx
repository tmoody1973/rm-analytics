import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'
import {
  chartSchema, tableSchema, normalizeChartData, CHART_TOOL, TABLE_TOOL, TableBlock,
  asPercent, pickFormatter,
} from './render-tools.jsx'
import { seriesColor, seriesColors, RM, SERIES } from './components.jsx'

describe('normalizeChartData', () => {
  const series = ['engagements']

  it('keeps a real zero as zero', () => {
    const [row] = normalizeChartData([{ month: '2026-01', engagements: 0 }], 'month', series)
    expect(row.engagements).toBe(0)
  })

  // The PR #25 lesson: a missing month means "not measured", never "zero".
  it('maps null, undefined and empty string to null — never to 0', () => {
    const rows = normalizeChartData(
      [{ month: 'a', engagements: null }, { month: 'b' }, { month: 'c', engagements: '' }],
      'month', series,
    )
    expect(rows.map((r) => r.engagements)).toEqual([null, null, null])
  })

  it('coerces numeric strings and preserves the x value verbatim', () => {
    const [row] = normalizeChartData([{ month: '2026-01', engagements: '1234' }], 'month', series)
    expect(row).toEqual({ month: '2026-01', engagements: 1234 })
  })
})

describe('schemas', () => {
  it('accepts a series with a null gap', () => {
    const parsed = chartSchema.parse({
      title: 'IG engagements', chart_type: 'line', x_key: 'month', series: ['hyfin'],
      data: [{ month: '2025-07', hyfin: null }, { month: '2025-08', hyfin: 900 }],
    })
    expect(parsed.data[0].hyfin).toBeNull()
  })

  // ChartBlock only branches on 'line' | 'bar'; the schema must not let anything else through.
  it('rejects a chart_type ChartBlock cannot draw', () => {
    expect(() => chartSchema.parse({
      title: 't', chart_type: 'pie', x_key: 'month', series: ['a'],
      data: [{ month: '1', a: 1 }, { month: '2', a: 2 }],
    })).toThrow()
  })
})

describe('value formatting (a rate must read as a %, not "1")', () => {
  it('formats a fraction as a percent — 0.86 → 86%, not rounded to 1', () => {
    expect(asPercent(0.86)).toBe('86%')
    expect(asPercent(0.0463)).toBe('4.6%')   // sub-10% keeps one decimal
    expect(asPercent(0)).toBe('0%')          // not "0.0%"
  })

  it('auto-detects a rate when value_format is omitted (all values within ±1.5)', () => {
    const rows = [{ m: 'a', r: 0.05 }, { m: 'b', r: 0.86 }]
    expect(pickFormatter(undefined, rows, ['r'])(0.86)).toBe('86%')
  })

  it('treats counts as counts, not percents', () => {
    const rows = [{ m: 'a', v: 1200 }, { m: 'b', v: 3400 }]
    expect(pickFormatter(undefined, rows, ['v'])(3400)).toBe('3.4K')
  })

  it('honors an explicit value_format over the heuristic', () => {
    const rows = [{ m: 'a', v: 0.5 }]
    expect(pickFormatter('currency', rows, ['v'])(1200)).toBe('$1.2K')
    expect(pickFormatter('number', rows, ['v'])(0.5)).toBe('0.5')
  })
})

describe('seriesColors (distinct per line — no two-blue collision)', () => {
  it('gives every series a different color, even when a label misses the brand map', () => {
    // The exact bug: 88nine.mke falls back to a palette blue that HYFIN already owns.
    const cols = seriesColors(['88Nine (radiomilwaukee)', '88Nine (88nine.mke)', 'HYFIN'])
    expect(new Set(cols).size).toBe(3)
    expect(cols).toContain(RM.blue)   // HYFIN keeps its brand blue
  })
})

describe('seriesColor', () => {
  it('paints a brand-named series in its brand color, in any casing', () => {
    expect(seriesColor('HYFIN', 3)).toBe(RM.blue)
    expect(seriesColor('88Nine', 1)).toBe(RM.orange)
  })

  it('falls back to the palette for a non-brand series', () => {
    expect(seriesColor('Total', 1)).toBe(SERIES[1])
  })
})

describe('tool definitions', () => {
  it('registers under the names the system prompt references', () => {
    expect(CHART_TOOL.name).toBe('render_chart')
    expect(TABLE_TOOL.name).toBe('render_table')
  })

  // A frontend tool with no handler yields an EMPTY tool-result message
  // (@copilotkit/core executeSpecificTool), and Anthropic rejects empty
  // tool_result content on the follow-up turn.
  it('returns a non-empty tool result so the follow-up turn is valid', async () => {
    for (const tool of [CHART_TOOL, TABLE_TOOL]) {
      const result = await tool.handler({})
      expect(typeof result).toBe('string')
      expect(result.length).toBeGreaterThan(0)
    }
  })
})

describe('TableBlock', () => {
  const html = renderToStaticMarkup(
    <TableBlock title="Top DMAs" columns={['DMA', 'TLH']} rows={[['Milwaukee', 1200], ['Chicago', null]]} />,
  )

  it('renders the title and a header cell per column', () => {
    expect(html).toContain('Top DMAs')
    expect(html.match(/<th>/g)).toHaveLength(2)
  })

  it('renders one body row per row', () => {
    expect(html.match(/<tr/g)).toHaveLength(3)   // 1 header + 2 body
  })

  it('renders a null cell as an em dash, not as 0 or blank', () => {
    expect(html).toContain('—')
    expect(html).not.toContain('>0<')
  })

  it('wraps the table in a horizontally scrollable container', () => {
    expect(html).toContain('chat-viz-scroll')
  })

  // A ragged row would otherwise slide values under the wrong header.
  it('pins every row to the header width, padding short rows and dropping extras', () => {
    const ragged = renderToStaticMarkup(
      <TableBlock title="t" columns={['A', 'B']} rows={[[1, 2, 3], [4]]} />,
    )
    const bodyRows = ragged.split('<tr>').slice(2)          // drop head + header row
    expect(bodyRows.map((r) => r.match(/<td/g).length)).toEqual([2, 2])
    expect(ragged).not.toContain('>3<')                     // the extra cell is dropped
    expect(bodyRows[1]).toContain('—')                      // the short row is padded
  })
})
