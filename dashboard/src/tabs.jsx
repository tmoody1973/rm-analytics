import React from 'react'
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
  fromStation, fromGaProperty, fromFbAccount, fromIgAccount, fromEmailList,
} from './brands.js'
import { BrandBadge, OrgWideBadge, NoBrandData } from './filters.jsx'
import { SECTION_INTRO, GLOSSARY, DECK } from './glossary.js'

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
          <Line key={s} type="monotone" dataKey={s} name={nameFmt(s)}
            stroke={stationColor(s) || SERIES[i % SERIES.length]} strokeWidth={2.4} dot={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

// ---------- OVERVIEW (org-wide snapshot — no brand/date filter) ----------
function Overview(d) {
  const k = d.exec_kpis[0]
  const reach = d.combined_digital_reach[0]
  return (
    <>
      <SectionTitle>At a glance</SectionTitle>
      <div className="grid cols-4">
        <Kpi label="Active Donors" value={num(k.active_donors)} note="Gave in last 12 months" />
        <Kpi label="Active Sustainers" value={num(k.active_sustainers)} note="Recurring plans" />
        <Kpi label="Sustainer MRR" value={money(k.sustainer_mrr)} accent note="Target $50K / mo" />
        <Kpi label="Revenue · 12 mo" value={money(k.revenue_12mo)} note="Completed gifts" />
      </div>
      <div className="grid cols-2">
        <ChartCard title="Revenue Trend (completed gifts)">
          <ResponsiveContainer width="100%" height={H}>
            <LineChart data={d.revenue_trend} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
              <CartesianGrid {...GRID} vertical={false} />
              <XAxis dataKey="month" {...AXIS} tickFormatter={(m) => m?.slice(0, 7)} />
              <YAxis {...AXIS} tickFormatter={moneyK} />
              <Tooltip {...TOOLTIP} formatter={(v) => money(v)} />
              <Line type="monotone" dataKey="revenue" stroke={RM.charcoal} strokeWidth={2.4}
                dot={{ r: 2, fill: RM.orange }} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Nielsen AQH Share — latest">
          <ResponsiveContainer width="100%" height={H}>
            <BarChart layout="vertical" data={d.nielsen_share} margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
              <CartesianGrid {...GRID} horizontal={false} />
              <XAxis type="number" {...AXIS} />
              <YAxis type="category" dataKey="station_code" {...AXIS} width={120} tickFormatter={stationLabel} />
              <Tooltip {...TOOLTIP} />
              <Bar dataKey="aqh_share" radius={[0, 4, 4, 0]}>
                {d.nielsen_share.map((r) => <Cell key={r.station_code} fill={stationColor(r.station_code)} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
      <div className="grid cols-4">
        <Kpi label="Web Sessions · 30d" value={num(reach.web_sessions_30d)} />
        <Kpi label="Social Reach · 30d" value={num(reach.social_reach_30d)} />
        <Kpi label="Emails Sent · 30d" value={num(reach.emails_sent_30d)} />
        <Kpi label="Donor Retention" value={pct(d.donor_retention[0].retention_pct)} accent note="Target 45–50%" />
      </div>
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
function DigitalReach(d, f) {
  const reach = d.combined_digital_reach[0]
  const web = filterByDate(filterByBrand(d.web_sessions_weekly, f.brand, 'property', fromGaProperty), 'week', f.range)
  const hasWeb = brandHasChannel(f.brand, 'web')
  const byWeek = sumBy(web, 'week', 'sessions').sort((a, b) => a.week.localeCompare(b.week))
  const totalSessions = byWeek.reduce((a, b) => a + b.sessions, 0)
  const latestWeek = (byWeek.at(-1) || {}).sessions
  const avgWeek = byWeek.length ? Math.round(totalSessions / byWeek.length) : null
  return (
    <>
      <SectionTitle>{SECTION_INTRO.digital} <BrandBadge brand={f.brand} /></SectionTitle>
      <div className="grid cols-4">
        <Kpi label={`Web Sessions · ${rangeLabel(f.range)}`} value={hasWeb ? num(totalSessions) : '—'} accent
          info={GLOSSARY.organic_traffic}
          note={hasWeb ? 'For the selected brand + period' : 'Not measured for this brand'} />
        <Kpi label="Avg / week" value={hasWeb ? num(avgWeek) : '—'} note="Selected period" />
        <Kpi label="Latest week" value={hasWeb ? num(latestWeek) : '—'} note="Most recent week" />
        <Kpi label="Org Web Sessions · 30d" value={num(reach.web_sessions_30d)} note="GA4 · org-wide" />
      </div>
      <ChartCard title="Website Sessions (weekly)" deck={DECK.top_web_content}>
        {!hasWeb ? <NoBrandData brand={f.brand} channel="web" />
          : <Lines rows={web} xKey="week" seriesKey="property" valKey="sessions" x={(w) => w?.slice(5)} nameFmt={propertyLabel} />}
      </ChartCard>
      <div className="note-flag">The first three counters reflect the selected brand and period; the last is the org-wide 30-day total. Facebook + Instagram live on the Social tab.</div>
    </>
  )
}

// ---------- SOCIAL (Facebook + Instagram) ----------
const igLatest = (rows, metric) => {
  if (!rows.length) return null
  const last = rows.reduce((m, r) => (r.month > m ? r.month : m), rows[0].month)
  return sum(rows.filter((r) => r.month === last).map((r) => Number(r[metric] || 0)))
}
const sum = (arr) => arr.reduce((a, b) => a + b, 0)

function Social(d, f) {
  const hasFb = brandHasChannel(f.brand, 'fb')
  const hasIg = brandHasChannel(f.brand, 'ig')
  const hasEmail = brandHasChannel(f.brand, 'email')

  // Email (Mailchimp) data
  const campsAll = filterByDate(filterByBrand(d.email_campaigns, f.brand, 'list_name', fromEmailList), 'sent', f.range)
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
      <div className="note-flag">Instagram reach/engagement is monthly (per account). Radio Milwaukee includes both @radiomilwaukee and @88nine.mke. Paid social (Meta Ads) is not yet connected.</div>

      {/* Email — Mailchimp widgets folded into the Social tab */}
      <SectionTitle>Email Marketing — Mailchimp <BrandBadge brand={f.brand} /></SectionTitle>
      {!hasEmail ? <NoBrandData brand={f.brand} channel="email" /> : (
        <>
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

  // Step 2: Headline KPIs — from tlh_by_station (monthly), pick latest month per station
  const tlhRows = filterByBrand(d.tlh_by_station || [], f.brand, 'station_code', fromStation)
  // Get the most recent month's row(s)
  const latestMonth = tlhRows.reduce((m, r) => (r.month > m ? r.month : m), '')
  const latestTlh = tlhRows.filter((r) => r.month === latestMonth)
  const totalTlh = latestTlh.reduce((a, r) => a + Number(r.tlh || 0), 0)
  const totalAas = latestTlh.reduce((a, r) => a + Number(r.aas || 0), 0)
  const totalCume = latestTlh.reduce((a, r) => a + Number(r.cume || 0), 0)
  // TSL: use latest month's tsl_minutes from tsl_trend if available, else from tlh_by_station
  const tslRows = filterByBrand(d.tsl_trend || [], f.brand, 'station_code', fromStation)
  const latestTslMonth = tslRows.reduce((m, r) => (r.month > m ? r.month : m), '')
  const latestTslRows = tslRows.filter((r) => r.month === latestTslMonth)
  const avgTslMin = latestTslRows.length
    ? latestTslRows.reduce((a, r) => a + Number(r.tsl_minutes || 0), 0) / latestTslRows.length
    : null
  const fmtTsl = (m) => (m == null ? '—' : `${Math.floor(m)}m ${Math.round((m % 1) * 60)}s`)

  // Step 3: Daypart AAS rows (passed to shared DaypartAas component)
  const daypartRows = filterByBrand(d.daypart_aas || [], f.brand, 'station_code', fromStation)

  // Step 4: Hour grid — period-agnostic
  const hourGridRows = filterByBrand(d.hourly_grid || [], f.brand, 'station_code', fromStation)

  // Step 5: TSL trend — filtered by brand + date
  const tslTrend = filterByDate(tslRows, 'month', f.range)

  // Step 6: TLH/AAS trend — from tlh_by_station, filtered by brand + date
  const tlhTrend = filterByDate(tlhRows, 'month', f.range)

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

      {/* Step 2: Headline KPIs */}
      <div className="grid cols-4">
        <Kpi label="TLH (latest month)" value={num(totalTlh || null)} accent info={GLOSSARY.tlh}
          note={latestMonth ? latestMonth.slice(0, 7) : 'No data'} />
        <Kpi label="AAS (latest month)" value={num(totalAas || null)} info={GLOSSARY.aas}
          note={latestMonth ? latestMonth.slice(0, 7) : 'No data'} />
        <Kpi label="CUME (latest month)" value={num(totalCume || null)} info={GLOSSARY.cume}
          note={latestMonth ? latestMonth.slice(0, 7) : 'No data'} />
        <Kpi label="Avg TSL (latest month)" value={fmtTsl(avgTslMin)} info={GLOSSARY.tsl}
          note={latestTslMonth ? latestTslMonth.slice(0, 7) : 'No data'} />
      </div>

      {/* Step 3: Daypart AAS — shared DaypartAas component */}
      <DaypartAas rows={daypartRows} deck={DECK.daypart_aas} />

      {/* Step 4: Hourly grid */}
      <ChartCard title="Hour × Day Listening Grid" deck={DECK.hourly_grid}>
        <HourGrid rows={hourGridRows} />
        <div className="note-flag">365-day average profile — date filter does not apply. Brand filter applies.</div>
      </ChartCard>

      {/* Step 5: TSL trend */}
      <ChartCard title="Time Spent Listening — Monthly Trend" deck={DECK.tsl_trend}>
        {tslTrend.length === 0 ? (
          <div className="note-flag">No TSL trend data for this selection.</div>
        ) : (
          <Lines rows={tslTrend} xKey="month" seriesKey="station_code" valKey="tsl_minutes"
            x={(m) => m?.slice(0, 7)} nameFmt={stationLabel} />
        )}
      </ChartCard>

      {/* Step 6: TLH/AAS/CUME trends */}
      <ChartCard title="Total Listening Hours — Monthly Trend">
        {tlhTrend.length === 0 ? (
          <div className="note-flag">No TLH data for this selection.</div>
        ) : (
          <Lines rows={tlhTrend} xKey="month" seriesKey="station_code" valKey="tlh"
            x={(m) => m?.slice(0, 7)} nameFmt={stationLabel} />
        )}
      </ChartCard>

      <ChartCard title="Average Active Sessions — Monthly Trend" info={GLOSSARY.aas}>
        {tlhTrend.length === 0 ? (
          <div className="note-flag">No AAS data for this selection.</div>
        ) : (
          <Lines rows={tlhTrend} xKey="month" seriesKey="station_code" valKey="aas"
            x={(m) => m?.slice(0, 7)} nameFmt={stationLabel} />
        )}
      </ChartCard>

      <ChartCard title="Cume — Monthly Trend" info={GLOSSARY.cume}>
        {tlhTrend.length === 0 ? (
          <div className="note-flag">No CUME data for this selection.</div>
        ) : (
          <Lines rows={tlhTrend} xKey="month" seriesKey="station_code" valKey="cume"
            x={(m) => m?.slice(0, 7)} nameFmt={stationLabel} />
        )}
      </ChartCard>

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
            <ChartCard title="Nielsen AQH Share Trend" deck={DECK.aqh_share_trend} info={GLOSSARY.aqh_share}>
              <Lines rows={nielsenTrend} xKey="period_label" seriesKey="station_code"
                valKey="aqh_share" x={(p) => p} nameFmt={stationLabel} />
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

// NOTE: Nielsen, Triton, and Mailchimp render functions are kept above and
// will be reused by ProgramDirector / Underwriting / Social in Tasks 5–6.
// They are intentionally NOT listed as TABS entries.

export const TABS = {
  Overview,
  'Program Director': ProgramDirector,
  Underwriting: UnderwritingTab,
  Digital: DigitalReach,
  Social,
  'Finance / Exec': Financial,
}
