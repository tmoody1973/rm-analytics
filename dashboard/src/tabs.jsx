import React from 'react'
import { HistoryView } from './history.jsx'
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar, AreaChart, Area,
  PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts'
import {
  RM, SERIES, AXIS, GRID, TOOLTIP, money, moneyK, num, pct,
  Kpi, ChartCard, SectionTitle, pivot, distinct, sumBy, HourGrid,
} from './components.jsx'
import {
  filterByBrand, filterByDate, brandHasChannel, stationLabel, propertyLabel, rangeLabel,
  fromStation, fromGaProperty, fromFbAccount, fromIgAccount, fromEmailList, pageTitle, rangeCutoff,
} from './brands.js'
import { BrandBadge, OrgWideBadge, NoBrandData } from './filters.jsx'
import { SECTION_INTRO, GLOSSARY, DECK } from './glossary.js'
import { StartHere } from './start-here.jsx'

const H = 300
const stationColor = (s) => (s === 'RM88' ? RM.orange : s === 'HYFIN' ? RM.blue : RM.charcoal70)

// Multi-series line chart. `nameFmt` relabels each series for legend/tooltip.
function Lines({ rows, xKey, seriesKey, valKey, x, nameFmt = (s) => s }) {
  const data = pivot(rows, xKey, seriesKey, valKey)
  const series = distinct(rows, seriesKey)
  return (
    <ResponsiveContainer width="100%" height={H}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
        <CartesianGrid {...GRID} vertical={false} />
        <XAxis dataKey={xKey} {...AXIS} tickFormatter={x} />
        <YAxis {...AXIS} />
        <Tooltip {...TOOLTIP} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {series.map((s, i) => (
          // connectNulls={false} is the Recharts default; stated so nobody "fixes" a gap
          // by turning it on. A gap means the month was never measured (pivot → null).
          <Line key={s} type="monotone" dataKey={s} name={nameFmt(s)} connectNulls={false}
            stroke={stationColor(s) || SERIES[i % SERIES.length]} strokeWidth={2.4} dot={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

// ---------- OVERVIEW — Board/Executive scorecard ----------

// Direction-arrow helper: compare latest trend point to same period prior year
// (fallback: prior available point). Returns {delta, dir: 'up'|'down'} or null.
function trendDirection(rows, dateKey, valKey) {
  if (!rows || rows.length < 2) return null
  const sorted = [...rows].sort((a, b) => String(a[dateKey]).localeCompare(String(b[dateKey])))
  const latest = sorted[sorted.length - 1]
  const latestVal = Number(latest[valKey])
  if (isNaN(latestVal)) return null
  // Try to find a row from ~12 months earlier (within ±2 months)
  const latestDate = new Date(latest[dateKey])
  const targetMs = latestDate.getTime() - 365 * 24 * 60 * 60 * 1000
  let priorRow = null
  let bestDiff = Infinity
  for (const r of sorted.slice(0, -1)) {
    const t = new Date(r[dateKey]).getTime()
    const diff = Math.abs(t - targetMs)
    if (diff < bestDiff && diff < 70 * 24 * 60 * 60 * 1000) { // within 70 days of target
      bestDiff = diff
      priorRow = r
    }
  }
  // Fallback: use the prior available point
  if (!priorRow) priorRow = sorted[sorted.length - 2]
  if (!priorRow) return null
  const priorVal = Number(priorRow[valKey])
  if (isNaN(priorVal) || priorVal === 0) return null
  const delta = latestVal - priorVal
  return { delta, dir: delta >= 0 ? 'up' : 'down' }
}

// Render direction badge inline: ▲ +123 or ▼ −456. Returns null when dir is null.
function Delta({ dir }) {
  if (!dir) return null
  const up = dir.dir === 'up'
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, marginLeft: 6,
      color: up ? '#2a7a3a' : '#c0392b',
    }}>
      {up ? '▲' : '▼'} {num(Math.abs(dir.delta))}
    </span>
  )
}

function Overview(d, f) {
  const k = d.exec_kpis[0] || {}
  const dk = d.dev_kpis || {}
  const st = d.sustainer_tracker[0] || {}
  const hdr = d.header[0] || {}

  // ── GROUP 1: Reach ──────────────────────────────────────────────
  // Broadcast: latest cume per station from nielsen_cume, direction from nielsen_cume_trend
  const bcRows = filterByBrand(d.nielsen_cume || [], f.brand, 'station_code', fromStation)
  const bcTrend = filterByBrand(d.nielsen_cume_trend || [], f.brand, 'station_code', fromStation)
  const hasBroadcast = brandHasChannel(f.brand, 'nielsen') && bcRows.length > 0
  // Build a per-station trend array for direction (group by station, sort by period_date)
  const bcTrendByStation = {}
  for (const r of bcTrend) {
    if (!bcTrendByStation[r.station_code]) bcTrendByStation[r.station_code] = []
    bcTrendByStation[r.station_code].push(r)
  }

  // Streaming cume: latest from station_comparison (brand-filtered), direction from tlh_by_station
  const streamRows = filterByBrand(d.station_comparison || [], f.brand, 'station_code', fromStation)
  const tlhHistory = filterByBrand(d.tlh_by_station || [], f.brand, 'station_code', fromStation)
  const totalStreamCume = streamRows.reduce((a, r) => a + Number(r.cume || 0), 0)
  const streamCumeDir = trendDirection(tlhHistory, 'month', 'cume')

  // Social followers: latest row per account, sum for the brand
  const socialFollowersAll = filterByBrand(d.social_followers || [], f.brand, 'account', fromFbAccount)
  // Get latest per account
  const latestFollowersByAccount = {}
  for (const r of socialFollowersAll) {
    if (!latestFollowersByAccount[r.account] || r.date > latestFollowersByAccount[r.account].date) {
      latestFollowersByAccount[r.account] = r
    }
  }
  const totalFollowers = Object.values(latestFollowersByAccount).reduce((a, r) => a + Number(r.followers || 0), 0)

  // Instagram followers: latest snapshot per account (ig_followers is already a single
  // latest-day snapshot from fact_ig_followers_daily), summed for the brand.
  const igFollowersRows = filterByBrand(d.ig_followers || [], f.brand, 'account_name', fromIgAccount)
  const totalIgFollowers = igFollowersRows.reduce((a, r) => a + Number(r.followers_count || 0), 0)

  // Web sessions: latest week total
  const webWeeklyAll = filterByBrand(d.web_sessions_weekly || [], f.brand, 'property', fromGaProperty)
  const latestWebWeek = webWeeklyAll.reduce((m, r) => (r.week > m ? r.week : m), '')
  const latestWebSessions = webWeeklyAll.filter((r) => r.week === latestWebWeek).reduce((a, r) => a + Number(r.sessions || 0), 0)
  const hasWeb = brandHasChannel(f.brand, 'web')

  // ── GROUP 2: Revenue ──────────────────────────────────────────────
  const latestRvb = (d.revenue_vs_budget || []).at(-1) || {}
  const revYtd = latestRvb.revenue_ytd || hdr.revenue_ytd
  const budgetYtd = latestRvb.budget_ytd
  const pctToBudget = hdr.pct_to_budget
  const latestMix = (d.revenue_mix || []).at(-1) || {}
  const revMixData = [
    { name: 'Foundation', value: latestMix.foundation },
    { name: 'Individual', value: latestMix.individual },
    { name: 'Underwriting', value: latestMix.underwriting },
  ].filter((x) => x.value)

  // ── GROUP 3: Donor health ─────────────────────────────────────────
  const mrrTarget = st.target || 50000
  const mrrVal = k.sustainer_mrr || st.mrr

  // ── GROUP 4: Market position ──────────────────────────────────────
  const nielsenShareRows = filterByBrand(d.nielsen_share || [], f.brand, 'station_code', fromStation)
  const aqhTrend = filterByBrand(d.nielsen_aqh_trend || [], f.brand, 'station_code', fromStation)
  const hasNielsen = brandHasChannel(f.brand, 'nielsen') && nielsenShareRows.length > 0

  return (
    <>
      {/* ── Intro ── */}
      <SectionTitle>{SECTION_INTRO.board} <OrgWideBadge /></SectionTitle>

      {/* ══════════════════════════════════════════════════════════
          GROUP 1 — REACH
      ════════════════════════════════════════════════════════════ */}
      <ChartCard title="Reach" deck={DECK.board_reach}>
        <div className="grid cols-4">
          {/* Broadcast weekly cume — only if brand has nielsen */}
          {hasBroadcast ? bcRows.map((r) => {
            const stDir = trendDirection(bcTrendByStation[r.station_code] || [], 'period_date', 'cume')
            return (
              <Kpi key={r.station_code}
                label={`${stationLabel(r.station_code)} Broadcast Cume`}
                value={<>{num(r.cume)}<Delta dir={stDir} /></>}
                info={GLOSSARY.weekly_cume}
                note="Weekly broadcast reach" />
            )
          }) : null}

          {/* Streaming cume */}
          {brandHasChannel(f.brand, 'streaming') ? (
            <Kpi label="Streaming Cume"
              value={<>{num(totalStreamCume || null)}<Delta dir={streamCumeDir} /></>}
              info={GLOSSARY.cume}
              note="Latest month · digital streams" />
          ) : null}

          {/* Social following — Facebook */}
          <Kpi label="Facebook Followers"
            value={num(totalFollowers || null)}
            note="Latest · Facebook" />

          {/* Social following — Instagram */}
          {totalIgFollowers > 0 ? (
            <Kpi label="Instagram Followers"
              value={num(totalIgFollowers)}
              note="Latest · Instagram" />
          ) : null}

          {/* Web sessions — latest week */}
          {hasWeb ? (
            <Kpi label="Web Sessions"
              value={num(latestWebSessions || null)}
              note={latestWebWeek ? `Week of ${latestWebWeek.slice(0, 10)}` : 'Latest week'} />
          ) : null}
        </div>
        <div className="note-flag">
          Broadcast, streaming, social, and web audiences are counted by source — a person who listens and donates appears in each bucket. We can&apos;t de-duplicate across them.
        </div>
      </ChartCard>

      {/* ══════════════════════════════════════════════════════════
          GROUP 2 — REVENUE VS BUDGET
      ════════════════════════════════════════════════════════════ */}
      <ChartCard title="Revenue vs. Budget" deck={DECK.board_revenue}>
        <OrgWideBadge />
        <div className="grid cols-4" style={{ marginTop: 12 }}>
          <Kpi label="Revenue YTD" value={money(revYtd)} accent />
          <Kpi label="Budget YTD" value={money(budgetYtd)} />
          <Kpi label="% to Budget" value={pctToBudget != null ? pct(pctToBudget) : '—'}
            accent={pctToBudget >= 100} info={GLOSSARY.pct_to_budget} note="Over 100% = ahead of plan" />
          <Kpi label="Surplus YTD" value={money(hdr.surplus_ytd)}
            note={hdr.cash_balance ? `Cash balance ${money(hdr.cash_balance)}` : undefined} />
        </div>
        {revMixData.length > 0 && (
          <div className="grid cols-2" style={{ marginTop: 16 }}>
            <ChartCard title="Revenue Breakdown (latest YTD)">
              <ResponsiveContainer width="100%" height={H}>
                <PieChart>
                  <Pie data={revMixData} dataKey="value" nameKey="name" innerRadius={64} outerRadius={104} paddingAngle={2}>
                    {revMixData.map((_, i) => <Cell key={i} fill={SERIES[i % SERIES.length]} />)}
                  </Pie>
                  <Tooltip {...TOOLTIP} formatter={(v) => money(v)} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            </ChartCard>
            <ChartCard title="Revenue vs. Budget (YTD trend)" deck={DECK.revenue_vs_budget}>
              <ResponsiveContainer width="100%" height={H}>
                <BarChart data={d.revenue_vs_budget || []} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
                  <CartesianGrid {...GRID} vertical={false} />
                  <XAxis dataKey="month" {...AXIS} tickFormatter={(m) => m?.slice(0, 7)} />
                  <YAxis {...AXIS} tickFormatter={moneyK} />
                  <Tooltip {...TOOLTIP} formatter={(v) => money(v)} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="revenue_ytd" name="Revenue" fill={RM.charcoal} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="budget_ytd" name="Budget" fill={RM.blueSoft} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>
        )}
      </ChartCard>

      {/* ══════════════════════════════════════════════════════════
          GROUP 3 — DONOR HEALTH
      ════════════════════════════════════════════════════════════ */}
      <ChartCard title="Donor Health" deck={DECK.board_donors}>
        <OrgWideBadge />
        <div className="grid cols-4" style={{ marginTop: 12 }}>
          <Kpi label="Active Donors"
            value={num(k.active_donors)}
            note="Gave in last 12 months" />
          <Kpi label="Active Sustainers"
            value={num(k.active_sustainers)}
            note="Recurring plans" />
          <Kpi label="Sustainer MRR"
            value={money(mrrVal)}
            accent={mrrVal >= mrrTarget}
            info={GLOSSARY.sustainer_mrr}
            note={mrrTarget ? `Target ${money(mrrTarget)} / mo` : 'Monthly recurring'} />
          <Kpi label="Donor Retention"
            value={pct(dk.donor_retention_pct)}
            info={GLOSSARY.donor_retention}
            note="Target 45–50% · prior-year donors who gave again" />
        </div>
      </ChartCard>

      {/* ══════════════════════════════════════════════════════════
          GROUP 4 — MARKET POSITION
      ════════════════════════════════════════════════════════════ */}
      <ChartCard title="Market Position" deck={DECK.board_market}>
        {!hasNielsen ? (
          <div className="note-flag">Nielsen data is available for Radio Milwaukee and HYFIN — select one of those brands, or All Brands, to see market position.</div>
        ) : (
          <>
            {/* AQH share + rank per station, with aqh_vs_cume context */}
            <div className="grid cols-2">
              {nielsenShareRows.map((r) => (
                <Kpi key={r.station_code}
                  label={`${stationLabel(r.station_code)} AQH Share`}
                  value={r.aqh_share != null ? `${r.aqh_share}%` : '—'}
                  accent={r.station_code === 'RM88'}
                  info={GLOSSARY.aqh_share}
                  note={r.rank ? `Market rank #${r.rank} · ${GLOSSARY.market_rank.split('.')[0]}` : undefined} />
              ))}
            </div>
            <div style={{ fontSize: 12, color: RM.charcoal70, margin: '8px 0 12px', fontStyle: 'italic' }}>
              {GLOSSARY.aqh_vs_cume}
            </div>
            {/* AQH persons sparkline */}
            {aqhTrend.length > 0 && (
              <ChartCard title="AQH Persons — Survey Trend" info={GLOSSARY.aqh_persons}>
                <Lines rows={aqhTrend} xKey="period_label" seriesKey="station_code"
                  valKey="aqh_persons" x={(p) => p} nameFmt={stationLabel} />
              </ChartCard>
            )}
          </>
        )}
      </ChartCard>
    </>
  )
}

// ---------- FINANCIAL (org-wide) ----------
function Financial(d, f) {
  const rvb = filterByDate(d.revenue_vs_budget, 'month', f.range)
  const latestMix = d.revenue_mix[d.revenue_mix.length - 1] || {}
  const mix = [
    { name: 'Foundation', value: latestMix.foundation },
    { name: 'Individual', value: latestMix.individual },
    { name: 'Underwriting', value: latestMix.underwriting },
  ].filter((x) => x.value)
  const last = rvb[rvb.length - 1] || {}
  return (
    <>
      <SectionTitle>{SECTION_INTRO.finance} <OrgWideBadge /></SectionTitle>
      <div className="grid cols-4">
        <Kpi label="Revenue YTD" value={money(last.revenue_ytd)} accent />
        <Kpi label="Budget YTD" value={money(last.budget_ytd)} />
        <Kpi label="Foundation" value={money(latestMix.foundation)} />
        <Kpi label="Individual + Underwriting" value={money((latestMix.individual || 0) + (latestMix.underwriting || 0))} />
      </div>
      <div className="grid cols-2">
        <ChartCard title="Revenue vs. Budget (YTD)" deck={DECK.revenue_vs_budget}>
          <ResponsiveContainer width="100%" height={H}>
            <BarChart data={rvb} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
              <CartesianGrid {...GRID} vertical={false} />
              <XAxis dataKey="month" {...AXIS} tickFormatter={(m) => m?.slice(0, 7)} />
              <YAxis {...AXIS} tickFormatter={moneyK} />
              <Tooltip {...TOOLTIP} formatter={(v) => money(v)} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="revenue_ytd" name="Revenue" fill={RM.charcoal} radius={[4, 4, 0, 0]} />
              <Bar dataKey="budget_ytd" name="Budget" fill={RM.blueSoft} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Revenue Breakdown (latest YTD)">
          <ResponsiveContainer width="100%" height={H}>
            <PieChart>
              <Pie data={mix} dataKey="value" nameKey="name" innerRadius={64} outerRadius={104} paddingAngle={2}>
                {mix.map((_, i) => <Cell key={i} fill={SERIES[i % SERIES.length]} />)}
              </Pie>
              <Tooltip {...TOOLTIP} formatter={(v) => money(v)} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
      <div className="note-flag">Finance is organization-wide (not split by brand). FY2026 YTD, Feb–Apr 2026 loaded. Underwriting pipeline / per-sponsor detail not yet in the warehouse.</div>
    </>
  )
}

// ---------- DIGITAL REACH (web) ----------
// Top-pages table: derived title (raw path on hover) + views/users/avg engagement.
// Views = reach, engagement time = whether they stayed — both, not just volume.
function TopPagesTable({ rows }) {
  if (!rows.length) return <div className="note-flag">No page data for this selection.</div>
  return (
    <table className="rm">
      <thead>
        <tr>
          <th>Page</th>
          <th className="num">Views</th>
          <th className="num">Users</th>
          <th className="num">Avg Eng.</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td title={r.page_path}
              style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {pageTitle(r.page_path)}
            </td>
            <td className="num">{num(r.views)}</td>
            <td className="num">{num(r.users)}</td>
            <td className="num">{r.avg_engagement_s != null ? `${Math.round(r.avg_engagement_s)}s` : '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// --- Web-overview helpers (Digital tab) ---
const UP = '#2f8f5b'      // green reads "up / good" at a glance
const DOWN = RM.red
const CHANNEL_COLOR = {
  'Organic Search': RM.blue, Direct: RM.orange, Paid: RM.charcoal,
  Referral: RM.blueSoft, Social: RM.charcoal70, Email: RM.red, Other: RM.charcoal70,
}
const fmtSecs = (s) => {
  s = Math.round(Number(s) || 0)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}
const humanizeEvent = (e) => String(e || '').replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
const pctDelta = (cur, prev) => (prev ? (cur - prev) / prev : null)

// KPI card with a period-over-period delta arrow (green up / red down).
function WebKpi({ label, value, delta, note, accent }) {
  let deltaEl = null
  if (delta != null && isFinite(delta)) {
    const up = delta >= 0
    deltaEl = (
      <div className="note" style={{ color: up ? UP : DOWN, fontWeight: 600 }}>
        {up ? '▲' : '▼'} {Math.abs(delta * 100).toFixed(1)}%
        <span style={{ color: 'var(--fg-subtle)', fontWeight: 400 }}> vs prior period</span>
      </div>
    )
  }
  return (
    <div className="card kpi">
      <div className="label">{label}</div>
      <div className={'value' + (accent ? ' accent' : '')}>{value}</div>
      {deltaEl}
      {note && <div className="note">{note}</div>}
    </div>
  )
}

// Aggregate daily web rows into headline numbers. Daily averages divide by
// DISTINCT dates so the ALL-brands view (two GA properties per date) isn't halved.
function aggWeb(rows) {
  const sum = (k) => rows.reduce((a, r) => a + Number(r[k] || 0), 0)
  const days = new Set(rows.map((r) => r.date)).size || 1
  const users = sum('users'), views = sum('views')
  const sessSec = rows.length ? sum('avg_session_sec') / rows.length : 0
  return {
    usersPerDay: users / days, viewsPerDay: views / days,
    pagesPerUser: users ? views / users : 0, sessSec,
  }
}

// Streaming daily aggregates — Listeners (avg daily CUME; non-additive, so it is
// averaged not summed), Sessions (avg daily SS), Sessions/User (SS÷CUME), and
// Minutes/Session (TLH×60÷SS). Matches the NPR streaming-overview definitions.
function aggStreaming(rows) {
  const sum = (k) => rows.reduce((a, r) => a + Number(r[k] || 0), 0)
  const days = new Set(rows.map((r) => r.date)).size || 1
  const cume = sum('cume'), ss = sum('ss'), tlh = sum('tlh')
  return {
    listenersPerDay: cume / days, sessionsPerDay: ss / days,
    sessPerUser: cume ? ss / cume : 0, minPerSession: ss ? tlh * 60 / ss : 0,
  }
}

// Split the brand-filtered daily series into the selected window and the
// equal-length window immediately before it (for the delta). All-time has no
// comparable prior window.
function webWindows(daily, rangeKey) {
  const cutoff = rangeCutoff(rangeKey)
  if (!cutoff) return { cur: daily, prev: [] }
  const cutMs = cutoff.getTime()
  const prevMs = cutMs - (Date.now() - cutMs)
  const t = (r) => new Date(r.date).getTime()
  return {
    cur: daily.filter((r) => t(r) >= cutMs),
    prev: daily.filter((r) => t(r) >= prevMs && t(r) < cutMs),
  }
}

function GeoTable({ rows, label }) {
  if (!rows.length) return <div className="note-flag">No location data.</div>
  return (
    <table className="rm">
      <thead><tr><th>{label}</th><th className="num">Sessions</th><th className="num">Users</th></tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}><td>{r.place}</td><td className="num">{num(r.sessions)}</td><td className="num">{num(r.users)}</td></tr>
        ))}
      </tbody>
    </table>
  )
}

function DigitalReach(d, f) {
  const hasWeb = brandHasChannel(f.brand, 'web')
  const reach = (d.combined_digital_reach || [])[0] || {}

  if (!hasWeb) {
    return (
      <>
        <SectionTitle>{SECTION_INTRO.digital} <BrandBadge brand={f.brand} /></SectionTitle>
        <NoBrandData brand={f.brand} channel="web" />
      </>
    )
  }

  // Daily series → KPI row + deltas + trends (honors brand + date filter).
  const daily = filterByBrand(d.web_daily || [], f.brand, 'property', fromGaProperty)
  const { cur, prev } = webWindows(daily, f.range)
  const a = aggWeb(cur), b = aggWeb(prev)
  const series = filterByDate(daily, 'date', f.range)
    .map((r) => ({ ...r, per_user: Number(r.users) ? Number(r.views) / Number(r.users) : 0 }))

  // Dimensional cards — trailing 30 days (the date filter does not apply).
  const channels = filterByBrand(d.web_channels || [], f.brand, 'property', fromGaProperty)
  const chanTotal = channels.reduce((s, r) => s + Number(r.sessions || 0), 0)
  const geo = filterByBrand(d.web_geo || [], f.brand, 'property', fromGaProperty)
  const regions = geo.filter((r) => r.level === 'region').slice(0, 8)
  const cities = geo.filter((r) => r.level === 'city').slice(0, 8)
  const devices = filterByBrand(d.web_devices || [], f.brand, 'property', fromGaProperty)
  const devTotal = devices.reduce((s, r) => s + Number(r.sessions || 0), 0)
  const events = filterByBrand(d.web_key_events || [], f.brand, 'property', fromGaProperty).slice(0, 8)
  const weeklyPages = filterByBrand(d.top_pages_weekly || [], f.brand, 'property', fromGaProperty).slice(0, 10)
  const monthlyPages = filterByBrand(d.top_pages_monthly || [], f.brand, 'property', fromGaProperty).slice(0, 10)

  const x = (dt) => String(dt).slice(5)

  return (
    <>
      <SectionTitle>{SECTION_INTRO.digital} <BrandBadge brand={f.brand} /></SectionTitle>

      <div className="grid cols-4">
        <WebKpi label={`Active Users · ${rangeLabel(f.range)}`} accent value={num(a.usersPerDay)}
          delta={pctDelta(a.usersPerDay, b.usersPerDay)} note="daily average" />
        <WebKpi label="Pageviews" value={num(a.viewsPerDay)}
          delta={pctDelta(a.viewsPerDay, b.viewsPerDay)} note="daily average" />
        <WebKpi label="Pages / User" value={a.pagesPerUser.toFixed(1)}
          delta={pctDelta(a.pagesPerUser, b.pagesPerUser)} note="views ÷ users" />
        <WebKpi label="Avg Session" value={fmtSecs(a.sessSec)}
          delta={pctDelta(a.sessSec, b.sessSec)} note="time on site" />
      </div>

      <div className="subhead">Are we growing?</div>
      <div className="grid cols-2">
        <ChartCard title="Active Users">
          <Lines rows={series} xKey="date" seriesKey="property" valKey="users" x={x} nameFmt={propertyLabel} />
        </ChartCard>
        <ChartCard title="Pageviews">
          <Lines rows={series} xKey="date" seriesKey="property" valKey="views" x={x} nameFmt={propertyLabel} />
        </ChartCard>
      </div>

      <div className="subhead">How engaged are visitors?</div>
      <div className="grid cols-2">
        <ChartCard title="Pages per User">
          <Lines rows={series} xKey="date" seriesKey="property" valKey="per_user" x={x} nameFmt={propertyLabel} />
        </ChartCard>
        <ChartCard title="Avg Session Duration (sec)">
          <Lines rows={series} xKey="date" seriesKey="property" valKey="avg_session_sec" x={x} nameFmt={propertyLabel} />
        </ChartCard>
      </div>

      <div className="subhead">How do people find us? · last 30 days</div>
      <div className="grid cols-2">
        <ChartCard title="Traffic Channels">
          {channels.length === 0 ? <div className="note-flag">No channel data.</div> : (
            <ResponsiveContainer width="100%" height={H}>
              <BarChart layout="vertical" data={channels} margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
                <CartesianGrid {...GRID} horizontal={false} />
                <XAxis type="number" {...AXIS} />
                <YAxis type="category" dataKey="channel" {...AXIS} width={110} />
                <Tooltip {...TOOLTIP} />
                <Bar dataKey="sessions" radius={[0, 4, 4, 0]}>
                  {channels.map((r) => <Cell key={r.channel} fill={CHANNEL_COLOR[r.channel] || RM.charcoal70} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
        <ChartCard title="Channel Detail">
          <table className="rm">
            <thead><tr><th>Channel</th><th className="num">Sessions</th><th className="num">Share</th><th className="num">Views/Session</th></tr></thead>
            <tbody>
              {channels.map((r, i) => (
                <tr key={i}>
                  <td>{r.channel}</td>
                  <td className="num">{num(r.sessions)}</td>
                  <td className="num">{chanTotal ? `${Math.round(100 * Number(r.sessions) / chanTotal)}%` : '—'}</td>
                  <td className="num">{Number(r.sessions) ? (Number(r.views) / Number(r.sessions)).toFixed(1) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ChartCard>
      </div>

      <div className="subhead">What are they reading?</div>
      <div className="grid cols-2">
        <ChartCard title="Top Pages · This Week" deck={DECK.top_pages_weekly}><TopPagesTable rows={weeklyPages} /></ChartCard>
        <ChartCard title="Top Pages · This Month" deck={DECK.top_pages_monthly}><TopPagesTable rows={monthlyPages} /></ChartCard>
      </div>

      <div className="subhead">Where is our audience? · last 30 days</div>
      <div className="grid cols-2">
        <ChartCard title="Top Regions"><GeoTable rows={regions} label="Region" /></ChartCard>
        <ChartCard title="Top Cities"><GeoTable rows={cities} label="City" /></ChartCard>
      </div>

      <div className="subhead">Devices & on-site actions · last 30 days</div>
      <div className="grid cols-2">
        <ChartCard title="Devices">
          <table className="rm">
            <thead><tr><th>Device</th><th className="num">Sessions</th><th className="num">Share</th></tr></thead>
            <tbody>
              {devices.map((r, i) => (
                <tr key={i}>
                  <td style={{ textTransform: 'capitalize' }}>{r.device}</td>
                  <td className="num">{num(r.sessions)}</td>
                  <td className="num">{devTotal ? `${Math.round(100 * Number(r.sessions) / devTotal)}%` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ChartCard>
        <ChartCard title="Top On-Site Actions">
          <table className="rm">
            <thead><tr><th>Action</th><th className="num">Count</th></tr></thead>
            <tbody>
              {events.map((r, i) => (
                <tr key={i}><td>{humanizeEvent(r.event)}</td><td className="num">{num(r.count)}</td></tr>
              ))}
            </tbody>
          </table>
        </ChartCard>
      </div>

      <div className="note-flag">
        Active Users, Pageviews and the trends honor the brand + date filter; channels, geography,
        devices and actions are the last 30 days. Org-wide web sessions (30d): {num(reach.web_sessions_30d)}.
        Facebook + Instagram live on the Social tab.
      </div>
    </>
  )
}

// ---------- SOCIAL (Facebook + Instagram) ----------
// The clean IG view (schema/022) returns NULL where the source can't be trusted.
// Skip those rows: fall back to the latest month that actually measured this
// metric, and return null (renders "—") if none did. Coercing NULL to 0 would
// swap a wrong big number for a wrong zero.
const igLatest = (rows, metric) => {
  const measured = rows.filter((r) => r[metric] != null)
  if (!measured.length) return null
  const last = measured.reduce((m, r) => (r.month > m ? r.month : m), measured[0].month)
  return sum(measured.filter((r) => r.month === last).map((r) => Number(r[metric])))
}
const sum = (arr) => arr.reduce((a, b) => a + b, 0)

function Social(d, f) {
  const hasFb = brandHasChannel(f.brand, 'fb')
  const hasIg = brandHasChannel(f.brand, 'ig')
  const hasEmail = brandHasChannel(f.brand, 'email')

  // Email (Mailchimp) data
  const campsAll = filterByDate(filterByBrand(d.email_campaigns || [], f.brand, 'list_name', fromEmailList), 'sent', f.range)
  const camps = campsAll.slice(0, 12)
  const lists = filterByBrand(d.email_lists || [], f.brand, 'list_name', fromEmailList)
  const members = lists.reduce((a, r) => a + Number(r.members || 0), 0)
  const emailsSent = campsAll.reduce((a, r) => a + Number(r.emails_sent || 0), 0)
  const openWeighted = emailsSent
    ? campsAll.reduce((a, r) => a + Number(r.open_rate || 0) * Number(r.emails_sent || 0), 0) / emailsSent
    : null

  if (!hasFb && !hasIg) {
    return (
      <>
        <SectionTitle>{SECTION_INTRO.social} <BrandBadge brand={f.brand} /></SectionTitle>
        <NoBrandData brand={f.brand} channel="social" />
        {hasEmail && (
          <>
            <SectionTitle>Email Marketing — Mailchimp <BrandBadge brand={f.brand} /></SectionTitle>
            <div className="grid cols-4">
              <Kpi label="List Members" value={num(members)} accent note="Current subscribers" />
              <Kpi label={`Emails Sent · ${rangeLabel(f.range)}`} value={num(emailsSent)} note="Across campaigns" />
              <Kpi label="Avg Open Rate" value={pct(openWeighted)} info={GLOSSARY.open_click_rate} note="Weighted by volume" />
              <Kpi label="Campaigns" value={num(campsAll.length)} note="In selected period" />
            </div>
          </>
        )}
      </>
    )
  }

  const fbRows = filterByDate(filterByBrand(d.social_followers, f.brand, 'account', fromFbAccount), 'date', f.range)
  const fb = sumBy(fbRows, 'date', 'followers').sort((a, b) => a.date.localeCompare(b.date))
  const ig = filterByDate(filterByBrand(d.social_ig_monthly, f.brand, 'account', fromIgAccount), 'month', f.range)
  return (
    <>
      <SectionTitle>{SECTION_INTRO.social} <BrandBadge brand={f.brand} /></SectionTitle>
      <div className="grid cols-4">
        <Kpi label="Facebook Followers" value={num((fb.at(-1) || {}).followers)} accent note="Latest" />
        <Kpi label="Instagram Reach" value={num(igLatest(ig, 'reach'))} info={GLOSSARY.reach} note="Latest month · unique people" />
        <Kpi label="Instagram Engagement" value={num(igLatest(ig, 'engagements'))} note="Latest month" />
        <Kpi label="IG Accounts Engaged" value={num(igLatest(ig, 'accounts_engaged'))} note="Latest month" />
      </div>
      <div className="grid cols-2">
        <ChartCard title="Instagram Reach (monthly)" info={GLOSSARY.reach}>
          {!hasIg ? <NoBrandData brand={f.brand} channel="Instagram" />
            : <Lines rows={ig} xKey="month" seriesKey="account" valKey="reach" x={(m) => m?.slice(0, 7)} />}
        </ChartCard>
        <ChartCard title="Instagram Engagement (monthly)" info={GLOSSARY.impressions}>
          {!hasIg ? <NoBrandData brand={f.brand} channel="Instagram" />
            : <Lines rows={ig} xKey="month" seriesKey="account" valKey="engagements" x={(m) => m?.slice(0, 7)} />}
        </ChartCard>
      </div>
      <ChartCard title="Facebook Followers">
        {!hasFb ? <NoBrandData brand={f.brand} channel="Facebook" /> : (
          <ResponsiveContainer width="100%" height={H}>
            <AreaChart data={fb} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
              <CartesianGrid {...GRID} vertical={false} />
              <XAxis dataKey="date" {...AXIS} tickFormatter={(x) => x?.slice(0, 7)} />
              <YAxis {...AXIS} domain={['dataMin - 200', 'dataMax + 200']} />
              <Tooltip {...TOOLTIP} />
              <Area type="monotone" dataKey="followers" stroke={RM.blue} fill={RM.blueSoft} fillOpacity={0.4} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </ChartCard>
      <div className="note-flag">Instagram reach/engagement is monthly (per account). Radio Milwaukee includes both @radiomilwaukee and @88nine.mke. Paid social (Meta Ads) is not yet connected. <strong>A break in a line means that month was never measured, not that the number was zero</strong> — Meta only began reporting engagement in August 2025.</div>

      {/* Email — Mailchimp widgets folded into the Social tab */}
      {hasEmail && (
        <>
          <SectionTitle>Email Marketing — Mailchimp <BrandBadge brand={f.brand} /></SectionTitle>
          <div className="grid cols-4">
            <Kpi label="List Members" value={num(members)} accent note="Current subscribers" />
            <Kpi label={`Emails Sent · ${rangeLabel(f.range)}`} value={num(emailsSent)} note="Across campaigns" />
            <Kpi label="Avg Open Rate" value={pct(openWeighted)} info={GLOSSARY.open_click_rate} note="Weighted by volume" />
            <Kpi label="Campaigns" value={num(campsAll.length)} note="In selected period" />
          </div>
          <ChartCard title="Open rate by campaign (recent)">
            <ResponsiveContainer width="100%" height={H}>
              <BarChart data={[...camps].reverse()} margin={{ top: 8, right: 16, bottom: 60, left: 4 }}>
                <CartesianGrid {...GRID} vertical={false} />
                <XAxis dataKey="campaign_title" {...AXIS} angle={-35} textAnchor="end" interval={0} height={70}
                  tickFormatter={(t) => (t || '').slice(0, 18)} />
                <YAxis {...AXIS} tickFormatter={(v) => pct(v)} />
                <Tooltip {...TOOLTIP} formatter={(v) => pct(v)} />
                <Bar dataKey="open_rate" fill={RM.orange} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
          <ChartCard title="Recent campaigns">
            <table className="rm">
              <thead><tr><th>Campaign</th><th>List</th><th>Sent</th><th className="num">Emails</th><th className="num">Open</th><th className="num">Click</th></tr></thead>
              <tbody>
                {camps.map((c, i) => (
                  <tr key={i}><td>{c.campaign_title}</td><td>{c.list_name}</td><td>{c.sent}</td><td className="num">{num(c.emails_sent)}</td>
                    <td className="num">{pct(c.open_rate)}</td><td className="num">{pct(c.click_rate)}</td></tr>
                ))}
              </tbody>
            </table>
          </ChartCard>
        </>
      )}
    </>
  )
}

// ---------- NIELSEN ----------
function Nielsen(d, f) {
  if (!brandHasChannel(f.brand, 'nielsen')) {
    return (
      <>
        <SectionTitle>Nielsen Ratings · P6+ · Milwaukee Market <BrandBadge brand={f.brand} /></SectionTitle>
        <NoBrandData brand={f.brand} channel="nielsen" />
      </>
    )
  }
  const share = filterByBrand(d.nielsen_share, f.brand, 'station_code', fromStation)
  const trend = filterByDate(filterByBrand(d.nielsen_aqh_trend, f.brand, 'station_code', fromStation), 'period_date', f.range)
  return (
    <>
      <SectionTitle>Nielsen Ratings · P6+ · Milwaukee Market <BrandBadge brand={f.brand} /></SectionTitle>
      <div className="grid cols-2">
        {share.map((r) => (
          <Kpi key={r.station_code} label={`${stationLabel(r.station_code)} AQH Share`} value={r.aqh_share}
            accent={r.station_code === 'RM88'} note={`Market rank #${r.rank}`} />
        ))}
      </div>
      <div className="grid cols-2">
        <ChartCard title="AQH Persons Trend">
          <Lines rows={trend} xKey="period_label" seriesKey="station_code" valKey="aqh_persons" x={(p) => p} nameFmt={stationLabel} />
        </ChartCard>
        <ChartCard title="AQH Share — latest">
          <ResponsiveContainer width="100%" height={H}>
            <BarChart layout="vertical" data={share} margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
              <CartesianGrid {...GRID} horizontal={false} />
              <XAxis type="number" {...AXIS} />
              <YAxis type="category" dataKey="station_code" {...AXIS} width={120} tickFormatter={stationLabel} />
              <Tooltip {...TOOLTIP} />
              <Bar dataKey="aqh_share" radius={[0, 4, 4, 0]}>
                {share.map((r) => <Cell key={r.station_code} fill={stationColor(r.station_code)} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
      <div className="note-flag">P6+ demo loaded (Radio Milwaukee = 88Nine FM, HYFIN). Additional demos/dayparts accumulate as reports are uploaded.</div>
    </>
  )
}

// ---------- TRITON STREAMING ----------
function Triton(d, f) {
  if (!brandHasChannel(f.brand, 'streaming')) {
    return (
      <>
        <SectionTitle>Digital Streaming — Triton · Monthly <BrandBadge brand={f.brand} /></SectionTitle>
        <NoBrandData brand={f.brand} channel="streaming" />
      </>
    )
  }
  const latest = filterByBrand(d.station_comparison, f.brand, 'station_code', fromStation)
  const tlh = filterByDate(filterByBrand(d.tlh_by_station, f.brand, 'station_code', fromStation), 'month', f.range)
  const deviceRows = filterByBrand(d.platform_breakdown, f.brand, 'station_code', fromStation)
  const platform = sumBy(deviceRows, 'device_family', 'tlh')
  return (
    <>
      <SectionTitle>Digital Streaming — Triton · Monthly <BrandBadge brand={f.brand} /></SectionTitle>
      <div className="grid cols-4">
        {latest.slice(0, 4).map((r) => (
          <Kpi key={r.station_code} label={`${stationLabel(r.station_code)} TLH`} value={num(r.tlh)} note={`AAS ${r.aas} · CUME ${num(r.cume)}`} />
        ))}
      </div>
      <div className="grid cols-2">
        <ChartCard title="Total Listening Hours by Station">
          <Lines rows={tlh} xKey="month" seriesKey="station_code" valKey="tlh" x={(m) => m?.slice(0, 7)} nameFmt={stationLabel} />
        </ChartCard>
        <ChartCard title="Platform Breakdown (TLH, latest month)">
          <ResponsiveContainer width="100%" height={H}>
            <PieChart>
              <Pie data={platform} dataKey="tlh" nameKey="device_family" innerRadius={60} outerRadius={104} paddingAngle={2}>
                {platform.map((_, i) => <Cell key={i} fill={SERIES[i % SERIES.length]} />)}
              </Pie>
              <Tooltip {...TOOLTIP} formatter={(v) => num(v)} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
      <ChartCard title="Station Comparison (latest month)">
        <table className="rm">
          <thead><tr><th>Station</th><th className="num">TLH</th><th className="num">AAS</th><th className="num">CUME</th></tr></thead>
          <tbody>
            {latest.map((r) => (
              <tr key={r.station_code}><td>{stationLabel(r.station_code)}</td><td className="num">{num(r.tlh)}</td><td className="num">{r.aas}</td><td className="num">{num(r.cume)}</td></tr>
            ))}
          </tbody>
        </table>
      </ChartCard>
    </>
  )
}

// ---------- MAILCHIMP ----------
function Mailchimp(d, f) {
  if (!brandHasChannel(f.brand, 'email')) {
    return (
      <>
        <SectionTitle>Email Marketing — Mailchimp <BrandBadge brand={f.brand} /></SectionTitle>
        <NoBrandData brand={f.brand} channel="email" />
      </>
    )
  }
  const campsAll = filterByDate(filterByBrand(d.email_campaigns, f.brand, 'list_name', fromEmailList), 'sent', f.range)
  const camps = campsAll.slice(0, 12)
  const lists = filterByBrand(d.email_lists || [], f.brand, 'list_name', fromEmailList)
  const members = lists.reduce((a, r) => a + Number(r.members || 0), 0)
  const emailsSent = campsAll.reduce((a, r) => a + Number(r.emails_sent || 0), 0)
  const openWeighted = emailsSent
    ? campsAll.reduce((a, r) => a + Number(r.open_rate || 0) * Number(r.emails_sent || 0), 0) / emailsSent
    : null
  return (
    <>
      <SectionTitle>Email Marketing — Mailchimp <BrandBadge brand={f.brand} /></SectionTitle>
      <div className="grid cols-4">
        <Kpi label="List Members" value={num(members)} accent note="Current subscribers" />
        <Kpi label={`Emails Sent · ${rangeLabel(f.range)}`} value={num(emailsSent)} note="Across campaigns" />
        <Kpi label="Avg Open Rate" value={pct(openWeighted)} note="Weighted by volume" />
        <Kpi label="Campaigns" value={num(campsAll.length)} note="In selected period" />
      </div>
      <ChartCard title="Open rate by campaign (recent)">
        <ResponsiveContainer width="100%" height={H}>
          <BarChart data={[...camps].reverse()} margin={{ top: 8, right: 16, bottom: 60, left: 4 }}>
            <CartesianGrid {...GRID} vertical={false} />
            <XAxis dataKey="campaign_title" {...AXIS} angle={-35} textAnchor="end" interval={0} height={70}
              tickFormatter={(t) => (t || '').slice(0, 18)} />
            <YAxis {...AXIS} tickFormatter={(v) => pct(v)} />
            <Tooltip {...TOOLTIP} formatter={(v) => pct(v)} />
            <Bar dataKey="open_rate" fill={RM.orange} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
      <ChartCard title="Recent campaigns">
        <table className="rm">
          <thead><tr><th>Campaign</th><th>List</th><th>Sent</th><th className="num">Emails</th><th className="num">Open</th><th className="num">Click</th></tr></thead>
          <tbody>
            {camps.map((c, i) => (
              <tr key={i}><td>{c.campaign_title}</td><td>{c.list_name}</td><td>{c.sent}</td><td className="num">{num(c.emails_sent)}</td>
                <td className="num">{pct(c.open_rate)}</td><td className="num">{pct(c.click_rate)}</td></tr>
            ))}
          </tbody>
        </table>
      </ChartCard>
    </>
  )
}

// ---------- SHARED: DaypartAas widget ----------
// Extracted so both ProgramDirector and UnderwritingTab can reuse it.
// `rows` is brand-filtered daypart_aas rows (with station_code, daypart_id, daypart, aas).
// `deck` is the ChartCard deck text passed by the caller.
function DaypartAas({ rows, deck }) {
  const daypartSorted = [...rows].sort((a, b) => Number(a.daypart_id) - Number(b.daypart_id))
  const daypartData = sumBy(daypartSorted.map((r) => ({ daypart: r.daypart, aas: r.aas })), 'daypart', 'aas')
    .sort((a, b) => {
      const ia = daypartSorted.findIndex((r) => r.daypart === a.daypart)
      const ib = daypartSorted.findIndex((r) => r.daypart === b.daypart)
      return ia - ib
    })
  return (
    <ChartCard title="Daypart — Average Active Sessions" deck={deck}>
      {daypartData.length === 0 ? (
        <div className="note-flag">No daypart data for this selection.</div>
      ) : (
        <ResponsiveContainer width="100%" height={H}>
          <BarChart data={daypartData} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid {...GRID} vertical={false} />
            <XAxis dataKey="daypart" {...AXIS} />
            <YAxis {...AXIS} />
            <Tooltip {...TOOLTIP} />
            <Bar dataKey="aas" name="AAS" fill={RM.blue} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
      <div className="note-flag">365-day profile — date filter does not apply. Brand filter applies.</div>
    </ChartCard>
  )
}

// ---------- PROGRAM DIRECTOR ----------
function ProgramDirector(d, f) {
  // Step 1: Gate the entire tab on streaming channel
  if (!brandHasChannel(f.brand, 'streaming')) {
    return (
      <>
        <SectionTitle>Program Director <BrandBadge brand={f.brand} /></SectionTitle>
        <NoBrandData brand={f.brand} channel="streaming" />
      </>
    )
  }

  // Streaming overview (NPR-style) — daily series powers the KPI row, deltas, and
  // trends; honors the brand + date filter. CUME is averaged, never summed.
  const sd = filterByBrand(d.streaming_daily || [], f.brand, 'station_code', fromStation)
  const { cur, prev } = webWindows(sd, f.range)
  const a = aggStreaming(cur), b = aggStreaming(prev)
  const x = (dt) => String(dt).slice(5)
  const sSeries = filterByDate(sd, 'date', f.range).map((r) => ({
    ...r,
    per_user: Number(r.cume) ? Number(r.ss) / Number(r.cume) : 0,
    min_session: Number(r.ss) ? Number(r.tlh) * 60 / Number(r.ss) : 0,
  }))
  // Listening by brand — TLH share across stations over the window (most useful
  // for All Brands; one row when a single brand is selected).
  const brandMix = Object.values(cur.reduce((acc, r) => {
    acc[r.station_code] = acc[r.station_code] || { station_code: r.station_code, tlh: 0 }
    acc[r.station_code].tlh += Number(r.tlh || 0)
    return acc
  }, {})).sort((p, q) => q.tlh - p.tlh)
  const brandMixTotal = brandMix.reduce((s, r) => s + r.tlh, 0) || 1
  // Device-family share, latest month — aggregate across the brand's station(s).
  const devAgg = Object.values(
    filterByBrand(d.streaming_devices || [], f.brand, 'station_code', fromStation)
      .filter((r) => r.device_family && String(r.device_family).trim())
      .reduce((acc, r) => {
        acc[r.device_family] = acc[r.device_family] || { device_family: r.device_family, ss: 0 }
        acc[r.device_family].ss += Number(r.ss || 0)
        return acc
      }, {})
  ).sort((p, q) => q.ss - p.ss)
  const devTotalSs = devAgg.reduce((s, r) => s + r.ss, 0) || 1

  // Daypart AAS + hour grid — period-agnostic depth, kept below the overview.
  const daypartRows = filterByBrand(d.daypart_aas || [], f.brand, 'station_code', fromStation)
  const hourGridRows = filterByBrand(d.hourly_grid || [], f.brand, 'station_code', fromStation)

  // Step 7: Nielsen — only if brand has nielsen
  const hasNielsen = brandHasChannel(f.brand, 'nielsen')
  const nielsenShare = filterByBrand(d.nielsen_share || [], f.brand, 'station_code', fromStation)
  const nielsenTrend = filterByDate(
    filterByBrand(d.nielsen_aqh_trend || [], f.brand, 'station_code', fromStation),
    'period_date', f.range
  )

  // Step 8: Top web content — only if brand has web
  const hasWeb = brandHasChannel(f.brand, 'web')
  const webContent = filterByBrand(d.top_web_content || [], f.brand, 'property', fromGaProperty)
    .slice(0, 15)

  return (
    <>
      <SectionTitle>
        {SECTION_INTRO.program_director} <BrandBadge brand={f.brand} />
      </SectionTitle>

      {/* NPR-style streaming KPI row — daily averages with period-over-period deltas */}
      <div className="grid cols-4">
        <WebKpi label={`Listeners · ${rangeLabel(f.range)}`} accent value={num(a.listenersPerDay)}
          delta={pctDelta(a.listenersPerDay, b.listenersPerDay)} note="daily average (cume)" />
        <WebKpi label="Sessions" value={num(a.sessionsPerDay)}
          delta={pctDelta(a.sessionsPerDay, b.sessionsPerDay)} note="daily average (starts)" />
        <WebKpi label="Sessions / User" value={a.sessPerUser.toFixed(1)}
          delta={pctDelta(a.sessPerUser, b.sessPerUser)} note="starts ÷ cume" />
        <WebKpi label="Minutes / Session" value={`${Math.round(a.minPerSession)} min`}
          delta={pctDelta(a.minPerSession, b.minPerSession)} note="listening ÷ sessions" />
      </div>

      {/* Step 3: Daypart AAS — shared DaypartAas component */}
      <DaypartAas rows={daypartRows} deck={DECK.daypart_aas} />

      {/* Step 4: Hourly grid */}
      <ChartCard title="Hour × Day Listening Grid" deck={DECK.hourly_grid}>
        <HourGrid rows={hourGridRows} />
        <div className="note-flag">365-day average profile — date filter does not apply. Brand filter applies.</div>
      </ChartCard>

      {/* NPR-style daily trends */}
      <div className="subhead">Are people listening?</div>
      <div className="grid cols-2">
        <ChartCard title="Listeners (daily)" info={GLOSSARY.cume}>
          <Lines rows={sSeries} xKey="date" seriesKey="station_code" valKey="cume" x={x} nameFmt={stationLabel} />
        </ChartCard>
        <ChartCard title="Sessions (daily)">
          <Lines rows={sSeries} xKey="date" seriesKey="station_code" valKey="ss" x={x} nameFmt={stationLabel} />
        </ChartCard>
      </div>
      <ChartCard title="Total Listening Hours (daily)" info={GLOSSARY.tlh}>
        <Lines rows={sSeries} xKey="date" seriesKey="station_code" valKey="tlh" x={x} nameFmt={stationLabel} />
      </ChartCard>

      <div className="subhead">How engaged are listeners?</div>
      <div className="grid cols-2">
        <ChartCard title="Sessions per User">
          <Lines rows={sSeries} xKey="date" seriesKey="station_code" valKey="per_user" x={x} nameFmt={stationLabel} />
        </ChartCard>
        <ChartCard title="Minutes per Session">
          <Lines rows={sSeries} xKey="date" seriesKey="station_code" valKey="min_session" x={x} nameFmt={stationLabel} />
        </ChartCard>
      </div>

      <div className="subhead">Listening mix · {rangeLabel(f.range)}</div>
      <div className="grid cols-2">
        <ChartCard title="Listening by Brand" info={GLOSSARY.tlh}>
          {brandMix.length === 0 ? <div className="note-flag">No data for this selection.</div> : (
            <table className="rm">
              <thead><tr><th>Brand</th><th className="num">Listening Hours</th><th className="num">Share</th></tr></thead>
              <tbody>
                {brandMix.map((r, i) => (
                  <tr key={i}>
                    <td>{stationLabel(r.station_code)}</td>
                    <td className="num">{num(r.tlh)}</td>
                    <td className="num">{Math.round(100 * r.tlh / brandMixTotal)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </ChartCard>
        <ChartCard title="Devices · latest month">
          {devAgg.length === 0 ? <div className="note-flag">No device data.</div> : (
            <table className="rm">
              <thead><tr><th>Device</th><th className="num">Sessions</th><th className="num">Share</th></tr></thead>
              <tbody>
                {devAgg.map((r, i) => (
                  <tr key={i}>
                    <td>{r.device_family}</td>
                    <td className="num">{num(r.ss)}</td>
                    <td className="num">{Math.round(100 * r.ss / devTotalSs)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </ChartCard>
      </div>

      {/* Step 7: Nielsen block */}
      {hasNielsen && (
        <>
          <div className="grid cols-2">
            {nielsenShare.map((r) => (
              <Kpi key={r.station_code} label={`${stationLabel(r.station_code)} AQH Share`}
                value={r.aqh_share} info={GLOSSARY.aqh_share}
                accent={r.station_code === 'RM88'} note={`Market rank #${r.rank}`} />
            ))}
          </div>
          <div className="grid cols-2">
            <ChartCard title="Nielsen AQH Persons — Trend" info={GLOSSARY.aqh_persons}>
              <Lines rows={nielsenTrend} xKey="period_label" seriesKey="station_code"
                valKey="aqh_persons" x={(p) => p} nameFmt={stationLabel} />
            </ChartCard>
            <ChartCard title="Nielsen AQH Share — latest">
              <ResponsiveContainer width="100%" height={H}>
                <BarChart layout="vertical" data={nielsenShare} margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
                  <CartesianGrid {...GRID} horizontal={false} />
                  <XAxis type="number" {...AXIS} />
                  <YAxis type="category" dataKey="station_code" {...AXIS} width={120} tickFormatter={stationLabel} />
                  <Tooltip {...TOOLTIP} />
                  <Bar dataKey="aqh_share" radius={[0, 4, 4, 0]}>
                    {nielsenShare.map((r) => <Cell key={r.station_code} fill={stationColor(r.station_code)} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>
          <div className="note-flag">P6+ demo loaded (Radio Milwaukee = 88Nine FM, HYFIN). Additional demos/dayparts accumulate as reports are uploaded.</div>
        </>
      )}

      {/* Step 8: Top web content (omit silently if no web channel) */}
      {hasWeb && (
        <ChartCard title="Top Web Content" deck={DECK.top_web_content}>
          {webContent.length === 0 ? (
            <div className="note-flag">No web content data for this selection.</div>
          ) : (
            <table className="rm">
              <thead>
                <tr>
                  <th>Page</th>
                  <th className="num">Views</th>
                  <th className="num">Avg Engagement</th>
                </tr>
              </thead>
              <tbody>
                {webContent.map((r, i) => (
                  <tr key={i}>
                    <td style={{ maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.page_path}
                    </td>
                    <td className="num">{num(r.views)}</td>
                    <td className="num">{r.avg_engagement_s != null ? `${Math.round(r.avg_engagement_s)}s` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </ChartCard>
      )}
    </>
  )
}

// ---------- UNDERWRITING ----------
function UnderwritingTab(d, f) {
  // Step 1: Gate entire tab on streaming channel
  if (!brandHasChannel(f.brand, 'streaming')) {
    return (
      <>
        <SectionTitle>{SECTION_INTRO.underwriting} <BrandBadge brand={f.brand} /></SectionTitle>
        <NoBrandData brand={f.brand} channel="streaming" />
      </>
    )
  }

  // Step 2: Sellable-inventory KPIs — overall AAS + per-daypart top
  const daypartRows = filterByBrand(d.daypart_aas || [], f.brand, 'station_code', fromStation)
  // Sum AAS across all dayparts (collapsed to daypart level, then total)
  const daypartSorted = [...daypartRows].sort((a, b) => Number(a.daypart_id) - Number(b.daypart_id))
  const daypartAggregated = sumBy(
    daypartSorted.map((r) => ({ daypart: r.daypart, daypart_id: r.daypart_id, aas: r.aas })),
    'daypart', 'aas'
  )
  // Overall AAS: average across dayparts (each daypart is already an average — don't sum them)
  const overallAas = daypartAggregated.length
    ? Math.round(daypartAggregated.reduce((a, r) => a + r.aas, 0) / daypartAggregated.length)
    : null
  // Top daypart by AAS
  const topDaypart = daypartAggregated.length
    ? daypartAggregated.reduce((best, r) => (r.aas > best.aas ? r : best), daypartAggregated[0])
    : null

  // Step 4: Device/platform split — brand-filtered via fromStation
  const deviceRows = filterByBrand(d.platform_breakdown || [], f.brand, 'station_code', fromStation)
  // platform_breakdown shape: {station_code, device_family, device, player, aas, tlh, cume, ss, tsl_minutes}
  // Collapse to device_family, summing tlh for the pie
  const deviceData = sumBy(deviceRows, 'device_family', 'tlh')

  // Step 5: Nielsen for advertisers — only if brand has nielsen
  const hasNielsen = brandHasChannel(f.brand, 'nielsen')
  const nielsenShare = filterByBrand(d.nielsen_share || [], f.brand, 'station_code', fromStation)
  const nielsenTrend = filterByDate(
    filterByBrand(d.nielsen_aqh_trend || [], f.brand, 'station_code', fromStation),
    'period_date', f.range
  )

  // Step 6: Revenue data (org-wide)
  const rvb = filterByDate(d.revenue_vs_budget || [], 'month', f.range)
  const latestMix = (d.revenue_mix || [])[d.revenue_mix ? d.revenue_mix.length - 1 : 0] || {}
  const last = rvb[rvb.length - 1] || {}

  return (
    <>
      <SectionTitle>{SECTION_INTRO.underwriting} <BrandBadge brand={f.brand} /></SectionTitle>

      {/* Step 2: Sellable-inventory KPIs */}
      <div className="grid cols-4">
        <Kpi label="Overall AAS" value={num(overallAas)} accent info={GLOSSARY.aas}
          note="Avg across dayparts · 365-day profile" />
        <Kpi label={`Top Daypart — ${topDaypart ? topDaypart.daypart : '—'}`}
          value={topDaypart ? num(Math.round(topDaypart.aas)) : '—'} info={GLOSSARY.aas}
          note="Highest avg concurrent streams" />
        <Kpi label="Device Segments" value={num(deviceData.length || null)} note="Distinct device families" />
        <Kpi label="Underwriting Revenue" value={money(latestMix.underwriting)} note="Latest YTD · org-wide" />
      </div>

      {/* Step 3: Marquee — shared DaypartAas widget */}
      <DaypartAas rows={daypartRows} deck="The audience we can sell, by time of day." />

      {/* Step 4: Device/platform split */}
      <ChartCard title="Device / Platform Split (TLH)" deck={DECK.device_split}>
        {deviceData.length === 0 ? (
          <div className="note-flag">No device data for this brand.</div>
        ) : (
          <ResponsiveContainer width="100%" height={H}>
            <PieChart>
              <Pie data={deviceData} dataKey="tlh" nameKey="device_family"
                innerRadius={60} outerRadius={104} paddingAngle={2}>
                {deviceData.map((_, i) => <Cell key={i} fill={SERIES[i % SERIES.length]} />)}
              </Pie>
              <Tooltip {...TOOLTIP} formatter={(v) => num(v)} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        )}
        <div className="note-flag">Latest month · based on Total Listening Hours by device family.</div>
      </ChartCard>

      {/* Step 5: Nielsen for advertisers */}
      {hasNielsen && (
        <>
          <div className="grid cols-2">
            {nielsenShare.map((r) => (
              <Kpi key={r.station_code} label={`${stationLabel(r.station_code)} AQH Persons`}
                value={num(r.aqh_persons)} info={GLOSSARY.aqh_persons}
                accent={r.station_code === 'RM88'} note={`Market rank #${r.rank}`} />
            ))}
          </div>
          <div className="grid cols-2">
            <ChartCard title="Nielsen AQH Persons — Trend" info={GLOSSARY.aqh_persons}>
              {nielsenTrend.length === 0 ? (
                <div className="note-flag">No Nielsen trend data for this period.</div>
              ) : (
                <Lines rows={nielsenTrend} xKey="period_label" seriesKey="station_code"
                  valKey="aqh_persons" x={(p) => p} nameFmt={stationLabel} />
              )}
            </ChartCard>
            <ChartCard title="Nielsen AQH Share — latest">
              <ResponsiveContainer width="100%" height={H}>
                <BarChart layout="vertical" data={nielsenShare} margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
                  <CartesianGrid {...GRID} horizontal={false} />
                  <XAxis type="number" {...AXIS} />
                  <YAxis type="category" dataKey="station_code" {...AXIS} width={120} tickFormatter={stationLabel} />
                  <Tooltip {...TOOLTIP} />
                  <Bar dataKey="aqh_share" radius={[0, 4, 4, 0]}>
                    {nielsenShare.map((r) => <Cell key={r.station_code} fill={stationColor(r.station_code)} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>
          <div className="note-flag">P6+ demo loaded (Radio Milwaukee = 88Nine FM, HYFIN). Additional demos/dayparts accumulate as reports are uploaded.</div>
        </>
      )}

      {/* Step 6: Underwriting revenue — org-wide */}
      <SectionTitle>Underwriting Revenue <OrgWideBadge /></SectionTitle>
      <div className="grid cols-4">
        <Kpi label="Revenue YTD" value={money(last.revenue_ytd)} accent />
        <Kpi label="Budget YTD" value={money(last.budget_ytd)} />
        <Kpi label="Underwriting (latest YTD)" value={money(latestMix.underwriting)} />
        <Kpi label="Individual + Underwriting" value={money((latestMix.individual || 0) + (latestMix.underwriting || 0))} />
      </div>
      <div className="grid cols-2">
        <ChartCard title="Revenue vs. Budget (YTD)" deck={DECK.revenue_vs_budget}>
          {rvb.length === 0 ? (
            <div className="note-flag">No revenue data loaded yet.</div>
          ) : (
            <ResponsiveContainer width="100%" height={H}>
              <BarChart data={rvb} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
                <CartesianGrid {...GRID} vertical={false} />
                <XAxis dataKey="month" {...AXIS} tickFormatter={(m) => m?.slice(0, 7)} />
                <YAxis {...AXIS} tickFormatter={moneyK} />
                <Tooltip {...TOOLTIP} formatter={(v) => money(v)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="revenue_ytd" name="Revenue" fill={RM.charcoal} radius={[4, 4, 0, 0]} />
                <Bar dataKey="budget_ytd" name="Budget" fill={RM.blueSoft} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
        <ChartCard title="Revenue Breakdown (latest YTD)">
          {(() => {
            const mix = [
              { name: 'Foundation', value: latestMix.foundation },
              { name: 'Individual', value: latestMix.individual },
              { name: 'Underwriting', value: latestMix.underwriting },
            ].filter((x) => x.value)
            return mix.length === 0 ? (
              <div className="note-flag">No revenue mix data loaded yet.</div>
            ) : (
              <ResponsiveContainer width="100%" height={H}>
                <PieChart>
                  <Pie data={mix} dataKey="value" nameKey="name" innerRadius={64} outerRadius={104} paddingAngle={2}>
                    {mix.map((_, i) => <Cell key={i} fill={SERIES[i % SERIES.length]} />)}
                  </Pie>
                  <Tooltip {...TOOLTIP} formatter={(v) => money(v)} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            )
          })()}
        </ChartCard>
      </div>
      <div className="note-flag"><em>Per-sponsor pipeline is coming once underwriting/CRM data is loaded.</em></div>
    </>
  )
}

// ---------- DEVELOPMENT (org-wide) ----------
function Development(d, f) {
  const k = d.exec_kpis[0]
  const dk = d.dev_kpis || {}

  // ── Step 3: Retention cohort — drop the latest prior_year (year+1 incomplete) ──
  const retentionRaw = d.donor_retention_trend || []
  const maxYear = retentionRaw.reduce((m, r) => Math.max(m, r.prior_year || 0), 0)
  // Drop rows where prior_year === maxYear (the forward-looking incomplete year)
  const retentionRows = retentionRaw.filter((r) => r.prior_year !== maxYear)
  const minYear = retentionRows.reduce((m, r) => Math.min(m, r.prior_year || 9999), 9999)

  // ── Step 4: New vs returning — filter by date (org-wide; no brand filter) ──
  const statusTrend = filterByDate(d.donor_status_trend || [], 'month', f.range)

  // ── Step 5: Sustainer flow — check if churn is all-zero ──
  const flowRaw = filterByDate(d.sustainer_flow || [], 'month', f.range)
  const allChurnZero = flowRaw.every((r) => !r.churned || Number(r.churned) === 0)

  // ── Step 6: LTV tiers — top-tier (last row, already ascending) ──
  const ltvTiers = d.ltv_tiers || []
  const topTier = ltvTiers[ltvTiers.length - 1] || {}
  const totalLtvDonors = ltvTiers.reduce((a, r) => a + Number(r.donors || 0), 0)
  const topTierPct = totalLtvDonors ? Math.round(100 * (topTier.donors || 0) / totalLtvDonors) : null

  // ── Step 7: Payment mix ──
  const payMix = d.payment_method_mix || []

  // ── Step 8: Donor geo ──
  const geoState = d.donor_geo_state || []
  const geoZip = d.donor_geo_zip || []

  return (
    <>
      {/* Step 1: Section intro */}
      <SectionTitle>{SECTION_INTRO.development} <OrgWideBadge /></SectionTitle>

      {/* Step 2: Headline KPI row */}
      <div className="grid cols-4">
        <Kpi label="Active Donors" value={num(k.active_donors)} accent note="Gave in last 12 months" />
        <Kpi label="Sustainer MRR" value={money(k.sustainer_mrr)} accent note="Target $50K / mo" />
        <Kpi label="Sustainer Share" value={pct(dk.sustainer_share)} info={GLOSSARY.sustainer_share}
          note="Of active donors, give monthly" />
        <Kpi label="Donor Retention" value={pct(dk.donor_retention_pct)} info={GLOSSARY.donor_retention}
          note="Prior-year donors who gave again" />
      </div>
      <div className="grid cols-4">
        <Kpi label="Median Gift" value={money(dk.avg_gift)} info={GLOSSARY.avg_gift}
          note={dk.avg_gift_mean != null ? `Mean ${money(dk.avg_gift_mean)}` : undefined} />
        <Kpi label="Revenue · 12 mo" value={money(k.revenue_12mo)} note="Completed gifts" />
        <Kpi label="Active Sustainers" value={num(k.active_sustainers)} note="Recurring plans" />
        <Kpi label="New Donors" value={num(dk.new_donors)} info={GLOSSARY.new_donor} note="First gift · last 12 mo" />
      </div>
      <div className="grid cols-4">
        <Kpi label="Lapsed Donors" value={num(dk.lapsed_donors)} info={GLOSSARY.lapsed_donor}
          note="Gave before; silent 12+ mo" />
      </div>

      {/* Step 3: Retention cohort chart */}
      <ChartCard title="Donor Retention by Cohort" deck={DECK.retention_cohort}>
        {retentionRows.length === 0 ? (
          <div className="note-flag">No retention cohort data available.</div>
        ) : (
          <Lines
            rows={retentionRows}
            xKey="prior_year"
            seriesKey="cohort"
            valKey="retention_pct"
            x={(y) => String(Math.round(Number(y)))}
            nameFmt={(s) => s === 'first_year' ? 'First-year donors' : 'Repeat donors'}
          />
        )}
        <div className="note-flag">
          {minYear !== 9999 && (
            <>The {minYear} bar is inflated — that&apos;s our 2023 data floor, so the &quot;prior year&quot; pool is artificially small. </>
          )}
          The most recent year ({maxYear}) is dropped because year+1 giving is still in progress.{' '}
          The {maxYear - 1} cohort is still in progress — its retention rate reflects only the giving collected so far in {maxYear} and will rise as the year completes.
        </div>
      </ChartCard>

      {/* Step 4: New vs returning donors */}
      <ChartCard title="New vs. Returning Donors (monthly)" deck={DECK.donor_status}>
        {statusTrend.length === 0 ? (
          <div className="note-flag">No donor status data for this period.</div>
        ) : (
          <ResponsiveContainer width="100%" height={H}>
            <BarChart data={statusTrend} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
              <CartesianGrid {...GRID} vertical={false} />
              <XAxis dataKey="month" {...AXIS} tickFormatter={(m) => m?.slice(0, 7)} />
              <YAxis {...AXIS} />
              <Tooltip {...TOOLTIP} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="new_donors" name="New donors" fill={RM.orange} radius={[4, 4, 0, 0]} stackId="a" />
              <Bar dataKey="returning_donors" name="Returning donors" fill={RM.blue} radius={[4, 4, 0, 0]} stackId="a" />
            </BarChart>
          </ResponsiveContainer>
        )}
      </ChartCard>

      {/* Step 5: Sustainer flow */}
      <ChartCard title="Sustainer Flow — Gained & Lost (monthly)" deck={DECK.sustainer_flow}>
        {flowRaw.length === 0 ? (
          <div className="note-flag">No sustainer flow data available.</div>
        ) : allChurnZero ? (
          <>
            <ResponsiveContainer width="100%" height={H}>
              <BarChart data={flowRaw} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
                <CartesianGrid {...GRID} vertical={false} />
                <XAxis dataKey="month" {...AXIS} tickFormatter={(m) => m?.slice(0, 7)} />
                <YAxis {...AXIS} />
                <Tooltip {...TOOLTIP} />
                <Bar dataKey="added" name="Added" fill={RM.blue} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <div className="note-flag">Cancellations aren&apos;t dated in the source yet — only new sustainers are charted.</div>
          </>
        ) : (
          <ResponsiveContainer width="100%" height={H}>
            <BarChart data={flowRaw} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
              <CartesianGrid {...GRID} vertical={false} />
              <XAxis dataKey="month" {...AXIS} tickFormatter={(m) => m?.slice(0, 7)} />
              <YAxis {...AXIS} />
              <Tooltip {...TOOLTIP} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="added" name="Added" fill={RM.blue} radius={[4, 4, 0, 0]} />
              <Bar dataKey="churned" name="Churned" fill={RM.red} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </ChartCard>

      {/* Step 6: LTV tiers */}
      <ChartCard title="Lifetime Value Tiers" deck={DECK.ltv_tiers}>
        {ltvTiers.length === 0 ? (
          <div className="note-flag">No LTV tier data available.</div>
        ) : (
          <>
            <table className="rm">
              <thead>
                <tr>
                  <th>Tier</th>
                  <th className="num">Donors</th>
                  <th className="num">Total Given</th>
                  <th className="num">% of Base</th>
                </tr>
              </thead>
              <tbody>
                {ltvTiers.map((r, i) => (
                  <tr key={i} style={r.tier === topTier.tier ? { fontWeight: 600, background: 'rgba(248,151,29,0.08)' } : undefined}>
                    <td>{r.tier}</td>
                    <td className="num">{num(r.donors)}</td>
                    <td className="num">{money(r.total)}</td>
                    <td className="num">{totalLtvDonors ? pct(100 * r.donors / totalLtvDonors) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {topTierPct != null && (
              <div className="note-flag">
                Top tier ({topTier.tier}) holds {topTierPct}% of donors but typically dominates total giving — the concentration that makes major gifts matter.
              </div>
            )}
          </>
        )}
      </ChartCard>

      {/* Step 7: Payment method mix */}
      <ChartCard title="Payment Method Mix" deck={DECK.payment_mix} info={GLOSSARY.payment_method}>
        {payMix.length === 0 ? (
          <div className="note-flag">No payment method data available.</div>
        ) : (
          <div className="grid cols-2">
            <ResponsiveContainer width="100%" height={H}>
              <BarChart layout="vertical" data={payMix} margin={{ top: 8, right: 24, bottom: 4, left: 0 }}>
                <CartesianGrid {...GRID} horizontal={false} />
                <XAxis type="number" {...AXIS} tickFormatter={num} />
                <YAxis type="category" dataKey="method" {...AXIS} width={100} />
                <Tooltip {...TOOLTIP} />
                <Bar dataKey="gifts" name="Gifts" fill={RM.blue} radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <ResponsiveContainer width="100%" height={H}>
              <BarChart layout="vertical" data={payMix} margin={{ top: 8, right: 24, bottom: 4, left: 0 }}>
                <CartesianGrid {...GRID} horizontal={false} />
                <XAxis type="number" {...AXIS} tickFormatter={moneyK} />
                <YAxis type="category" dataKey="method" {...AXIS} width={100} />
                <Tooltip {...TOOLTIP} formatter={(v) => money(v)} />
                <Bar dataKey="total" name="Total $" fill={RM.orange} radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </ChartCard>

      {/* Step 8: Donor geography — two tables side by side */}
      <ChartCard title="Donor Geography" deck={DECK.donor_geo}>
        {geoState.length === 0 && geoZip.length === 0 ? (
          <div className="note-flag">No geography data available.</div>
        ) : (
          <div className="grid cols-2">
            <table className="rm">
              <thead><tr><th>State</th><th className="num">Donors</th><th className="num">Lifetime</th></tr></thead>
              <tbody>
                {geoState.map((r, i) => (
                  <tr key={i}><td>{r.state}</td><td className="num">{num(r.donors)}</td><td className="num">{money(r.lifetime)}</td></tr>
                ))}
              </tbody>
            </table>
            <table className="rm">
              <thead><tr><th>ZIP</th><th className="num">Donors</th><th className="num">Lifetime</th></tr></thead>
              <tbody>
                {geoZip.map((r, i) => (
                  <tr key={i}><td>{r.zip}</td><td className="num">{num(r.donors)}</td><td className="num">{money(r.lifetime)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </ChartCard>

      {/* Step 9: Audience → giving funnel placeholder */}
      <p style={{ fontStyle: 'italic', color: 'var(--rm-charcoal70, #3A4146)', fontSize: 13, marginTop: 8 }}>
        Coming once the email source is connected — we&apos;ll show how audience turns into giving.
      </p>
    </>
  )
}

// NOTE: Nielsen, Triton, and Mailchimp render functions are kept above and
// will be reused by ProgramDirector / Underwriting / Social in Tasks 5–6.
// They are intentionally NOT listed as TABS entries.

export const TABS = {
  'Start Here': () => <StartHere />,
  Overview,
  'Program Director': ProgramDirector,
  Underwriting: UnderwritingTab,
  Development,
  Digital: DigitalReach,
  Social,
  'Finance / Exec': Financial,
  History: () => <HistoryView />,
}
