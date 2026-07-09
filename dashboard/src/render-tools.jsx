/**
 * Generative UI — the assistant draws its answer instead of narrating it.
 *
 * Two CopilotKit *frontend* tools. The model calls them with data it has already
 * fetched via the server tools (get_metric / query_sql / …); we render the result
 * inline in the chat. Nothing here touches the warehouse.
 *
 * Both tools carry a `handler`: a frontend tool without one produces an EMPTY
 * tool-result message (@copilotkit/core `executeSpecificTool`), and Anthropic
 * rejects empty tool_result content on the follow-up turn.
 */
import React from 'react'
import { z } from 'zod'
import { useFrontendTool } from '@copilotkit/react-core/v2'
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts'
import { brandColor, seriesColor, toNumOrNull, SERIES, AXIS, GRID, TOOLTIP, num } from './components.jsx'

const H = 220   // the sidebar is ~400px wide; the dashboard's 300 is too tall here

// Six-digit ticks ("140,000") overflow a y-axis narrow enough to leave room for the
// plot in a ~400px panel, and render clipped. Compact them: 140K.
const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 })
const tick = (v) => (typeof v === 'number' ? compact.format(v) : v)

const cell = z.union([z.string(), z.number()]).nullable()

export const chartSchema = z.object({
  title: z.string().describe('Short chart title, e.g. "HYFIN monthly engagements"'),
  chart_type: z.enum(['line', 'bar']).describe('line for change over time, bar for comparison across categories'),
  x_key: z.string().describe('The key in each data row holding the x-axis label, e.g. "month"'),
  series: z.array(z.string()).min(1).describe('One key per plotted line/bar, e.g. ["88Nine","HYFIN"]. These become the legend labels.'),
  data: z.array(z.record(cell)).min(2).describe('Rows of {x_key: label, ...series values}. Use null — never 0 — where a value was not measured.'),
  y_label: z.string().optional().describe('What the y-axis counts, e.g. "Listening hours"'),
})

export const tableSchema = z.object({
  title: z.string().describe('Short table title'),
  columns: z.array(z.string()).min(1).describe('Header labels, left to right'),
  rows: z.array(z.array(cell)).min(1).describe('One array per row, same length and order as columns. Use null for a missing value.'),
})

/**
 * Coerce only the series columns to numbers; the x value passes through verbatim
 * (it is usually a date or a category label). Missing values become `null`, never 0 —
 * see `toNumOrNull`, which `pivot` shares.
 */
export function normalizeChartData(data, xKey, series) {
  return (data ?? []).map((row) => {
    const out = { [xKey]: row?.[xKey] }
    for (const key of series ?? []) out[key] = toNumOrNull(row?.[key])
    return out
  })
}

export function ChartBlock({ title, chart_type, x_key, series, data, y_label }) {
  // Args stream in partially while the model is still writing the tool call.
  if (!x_key || !series?.length || !data?.length) return null

  const rows = normalizeChartData(data, x_key, series)
  const Chart = chart_type === 'bar' ? BarChart : LineChart
  // A one-series bar chart is a comparison ACROSS categories ("TLH by brand"), so the
  // brand lives on the x-axis, not in the series name. Color each bar by its category.
  const perCategory = chart_type === 'bar' && series.length === 1

  return (
    <div className="chat-viz">
      <div className="chat-viz-title">{title}</div>
      <ResponsiveContainer width="100%" height={H}>
        <Chart data={rows} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid {...GRID} vertical={false} />
          <XAxis dataKey={x_key} {...AXIS} />
          <YAxis {...AXIS} width={44} tickFormatter={tick} />
          <Tooltip {...TOOLTIP} formatter={num} />
          {series.length > 1 ? <Legend wrapperStyle={{ fontSize: 11 }} /> : null}
          {series.map((key, i) =>
            chart_type === 'bar'
              ? (
                <Bar key={key} dataKey={key} fill={seriesColor(key, i)} radius={[3, 3, 0, 0]}>
                  {perCategory
                    ? rows.map((row, r) => <Cell key={r} fill={brandColor(row[x_key]) ?? SERIES[0]} />)
                    : null}
                </Bar>
              )
              : <Line key={key} type="monotone" dataKey={key} stroke={seriesColor(key, i)}
                  strokeWidth={2.2} dot={false} connectNulls={false} />,
          )}
        </Chart>
      </ResponsiveContainer>
      {y_label ? <div className="chat-viz-note">{y_label}</div> : null}
    </div>
  )
}

export function TableBlock({ title, columns, rows }) {
  if (!columns?.length || !rows?.length) return null
  return (
    <div className="chat-viz">
      <div className="chat-viz-title">{title}</div>
      <div className="chat-viz-scroll">
        <table className="rm">
          <thead>
            <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, r) => (
              <tr key={r}>
                {/* Pin every row to the header's width. A ragged row from the model would
                    otherwise slide values under the wrong column — silently wrong, which is
                    worse than a blank cell. */}
                {columns.map((_, c) => {
                  const v = row?.[c] ?? null
                  return (
                    <td key={c} className={typeof v === 'number' ? 'num' : undefined}>
                      {v === null ? '—' : typeof v === 'number' ? num(v) : v}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// The handler's return value becomes the tool-result message the model reads on
// its follow-up turn. Keep it terse and directive — it is the last thing the
// model sees before writing its sentence.
export const CHART_TOOL = {
  name: 'render_chart',
  description:
    'Draw a line or bar chart in the chat. Call this INSTEAD of listing a time series or a ' +
    'cross-brand comparison in prose. Pass data you already fetched from another tool.',
  parameters: chartSchema,
  handler: async () => 'Chart is now displayed to the user. Do not repeat its values in prose.',
}

export const TABLE_TOOL = {
  name: 'render_table',
  description:
    'Draw a table in the chat. Call this INSTEAD of writing out rows of data in prose. ' +
    'Pass data you already fetched from another tool.',
  parameters: tableSchema,
  handler: async () => 'Table is now displayed to the user. Do not repeat its rows in prose.',
}

/** Registers both tools. Must be mounted inside <CopilotKit>. Renders nothing itself. */
export function RenderTools() {
  useFrontendTool({ ...CHART_TOOL, render: ({ args }) => <ChartBlock {...args} /> }, [])
  useFrontendTool({ ...TABLE_TOOL, render: ({ args }) => <TableBlock {...args} /> }, [])
  return null
}
