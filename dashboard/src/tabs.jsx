import React from 'react'
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar, AreaChart, Area,
  PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts'
import {
  RM, SERIES, AXIS, GRID, TOOLTIP, money, moneyK, num, pct,
  Kpi, ChartCard, SectionTitle, pivot, distinct,
} from './components.jsx'

const H = 300
const stationColor = (s) => (s === 'RM88' ? RM.orange : s === 'HYFIN' ? RM.blue : RM.charcoal70)

function Lines({ rows, xKey, seriesKey, valKey, x }) {
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
          <Line key={s} type="monotone" dataKey={s} stroke={stationColor(s) || SERIES[i % SERIES.length]}
            strokeWidth={2.4} dot={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

// ---------- OVERVIEW ----------
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
              <YAxis type="category" dataKey="station_code" {...AXIS} width={70} />
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

// ---------- FINANCIAL ----------
function Financial(d) {
  const rvb = d.revenue_vs_budget
  const latestMix = d.revenue_mix[d.revenue_mix.length - 1] || {}
  const mix = [
    { name: 'Foundation', value: latestMix.foundation },
    { name: 'Individual', value: latestMix.individual },
    { name: 'Underwriting', value: latestMix.underwriting },
  ].filter((x) => x.value)
  const last = rvb[rvb.length - 1] || {}
  return (
    <>
      <SectionTitle>Financial Performance · FY2026 YTD</SectionTitle>
      <div className="grid cols-4">
        <Kpi label="Revenue YTD" value={money(last.revenue_ytd)} accent />
        <Kpi label="Budget YTD" value={money(last.budget_ytd)} />
        <Kpi label="Foundation" value={money(latestMix.foundation)} />
        <Kpi label="Individual + Underwriting" value={money((latestMix.individual || 0) + (latestMix.underwriting || 0))} />
      </div>
      <div className="grid cols-2">
        <ChartCard title="Revenue vs. Budget (YTD)">
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
      <div className="note-flag">Finance figures are FY2026 YTD (Feb–Apr 2026 loaded). Underwriting pipeline / per-sponsor detail not yet in the warehouse.</div>
    </>
  )
}

// ---------- DIGITAL REACH ----------
function DigitalReach(d) {
  const reach = d.combined_digital_reach[0]
  return (
    <>
      <SectionTitle>Combined Digital Reach · Web + Social + Email</SectionTitle>
      <div className="grid cols-4">
        <Kpi label="Web Sessions · 30d" value={num(reach.web_sessions_30d)} note="GA4" />
        <Kpi label="Social Reach · 30d" value={num(reach.social_reach_30d)} note="FB + IG" />
        <Kpi label="Emails Sent · 30d" value={num(reach.emails_sent_30d)} note="Mailchimp" />
        <Kpi label="FB Followers" value={num((d.social_followers.at(-1) || {}).followers)} accent />
      </div>
      <div className="grid cols-2">
        <ChartCard title="Website Sessions (weekly, 90d)">
          <Lines rows={d.web_sessions_weekly} xKey="week" seriesKey="property" valKey="sessions" x={(w) => w?.slice(5)} />
        </ChartCard>
        <ChartCard title="Facebook Followers">
          <ResponsiveContainer width="100%" height={H}>
            <AreaChart data={d.social_followers} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
              <CartesianGrid {...GRID} vertical={false} />
              <XAxis dataKey="date" {...AXIS} tickFormatter={(x) => x?.slice(0, 7)} />
              <YAxis {...AXIS} domain={['dataMin - 200', 'dataMax + 200']} />
              <Tooltip {...TOOLTIP} />
              <Area type="monotone" dataKey="followers" stroke={RM.blue} fill={RM.blueSoft} fillOpacity={0.4} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
      <div className="note-flag">Social = Facebook organic + IG reach currently loaded. Per-account FB/IG breakdown pending additional Meta connections.</div>
    </>
  )
}

// ---------- NIELSEN ----------
function Nielsen(d) {
  return (
    <>
      <SectionTitle>Nielsen Ratings · P6+ · Milwaukee Market</SectionTitle>
      <div className="grid cols-2">
        {d.nielsen_share.map((r) => (
          <Kpi key={r.station_code} label={`${r.station_code} AQH Share`} value={r.aqh_share}
            accent={r.station_code === 'RM88'} note={`Market rank #${r.rank}`} />
        ))}
      </div>
      <div className="grid cols-2">
        <ChartCard title="AQH Persons Trend">
          <Lines rows={d.nielsen_aqh_trend} xKey="period_label" seriesKey="station_code" valKey="aqh_persons" x={(p) => p} />
        </ChartCard>
        <ChartCard title="AQH Share — latest">
          <ResponsiveContainer width="100%" height={H}>
            <BarChart layout="vertical" data={d.nielsen_share} margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
              <CartesianGrid {...GRID} horizontal={false} />
              <XAxis type="number" {...AXIS} />
              <YAxis type="category" dataKey="station_code" {...AXIS} width={70} />
              <Tooltip {...TOOLTIP} />
              <Bar dataKey="aqh_share" radius={[0, 4, 4, 0]}>
                {d.nielsen_share.map((r) => <Cell key={r.station_code} fill={stationColor(r.station_code)} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
      <div className="note-flag">P6+ demo loaded (RM88 = 88Nine FM, HYFIN). Additional demos/dayparts accumulate as reports are uploaded.</div>
    </>
  )
}

// ---------- TRITON STREAMING ----------
function Triton(d) {
  const latest = d.station_comparison
  return (
    <>
      <SectionTitle>Digital Streaming — Triton · Monthly</SectionTitle>
      <div className="grid cols-4">
        {latest.slice(0, 4).map((r) => (
          <Kpi key={r.station_code} label={`${r.station_code} TLH`} value={num(r.tlh)} note={`AAS ${r.aas} · CUME ${num(r.cume)}`} />
        ))}
      </div>
      <div className="grid cols-2">
        <ChartCard title="Total Listening Hours by Station">
          <Lines rows={d.tlh_by_station} xKey="month" seriesKey="station_code" valKey="tlh" x={(m) => m?.slice(0, 7)} />
        </ChartCard>
        <ChartCard title="Platform Breakdown (TLH, latest month)">
          <ResponsiveContainer width="100%" height={H}>
            <PieChart>
              <Pie data={d.platform_breakdown} dataKey="tlh" nameKey="device_family" innerRadius={60} outerRadius={104} paddingAngle={2}>
                {d.platform_breakdown.map((_, i) => <Cell key={i} fill={SERIES[i % SERIES.length]} />)}
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
              <tr key={r.station_code}><td>{r.station_code}</td><td className="num">{num(r.tlh)}</td><td className="num">{r.aas}</td><td className="num">{num(r.cume)}</td></tr>
            ))}
          </tbody>
        </table>
      </ChartCard>
    </>
  )
}

// ---------- MAILCHIMP ----------
function Mailchimp(d) {
  const camps = d.email_campaigns
  return (
    <>
      <SectionTitle>Email Marketing — Mailchimp</SectionTitle>
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
          <thead><tr><th>Campaign</th><th>Sent</th><th className="num">Emails</th><th className="num">Open</th><th className="num">Click</th></tr></thead>
          <tbody>
            {camps.map((c, i) => (
              <tr key={i}><td>{c.campaign_title}</td><td>{c.sent}</td><td className="num">{num(c.emails_sent)}</td>
                <td className="num">{pct(c.open_rate)}</td><td className="num">{pct(c.click_rate)}</td></tr>
            ))}
          </tbody>
        </table>
      </ChartCard>
    </>
  )
}

export const TABS = {
  Overview, Financial, 'Digital Reach': DigitalReach, Nielsen, 'Triton Streaming': Triton, Mailchimp,
}
