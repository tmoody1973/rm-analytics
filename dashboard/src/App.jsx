import React, { useEffect, useState } from 'react'
import { fetchDashboard } from './api.js'
import { HeaderKpi, money, num } from './components.jsx'
import { FilterBar } from './filters.jsx'
import { ALL, DEFAULT_RANGE } from './brands.js'
import { TABS } from './tabs.jsx'

export default function App() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [tab, setTab] = useState('Overview')
  const [brand, setBrand] = useState(ALL)
  const [range, setRange] = useState(DEFAULT_RANGE)

  useEffect(() => {
    fetchDashboard().then(setData).catch((e) => setErr(e.message))
  }, [])

  const h = (data && data.header && data.header[0]) || {}
  const filters = { brand, range }

  return (
    <div className="app">
      <header className="hero">
        <div className="hero-top">
          <img className="logo" src="/assets/logo.png" alt="Radio Milwaukee" />
          <span className="live-pill"><span className="live-dot" />Live Dashboard</span>
        </div>
        <h1>Executive Performance Dashboard</h1>
        <div className="sub">Board of Directors · FY2026 YTD</div>
        <div className="kpi-strip">
          <HeaderKpi label="Revenue YTD" value={money(h.revenue_ytd)} note={h.pct_to_budget != null ? `${h.pct_to_budget}% to annual budget` : ''} />
          <HeaderKpi label="Cash Balance" value={money(h.cash_balance)} note="Current" />
          <HeaderKpi label="Total Donors YTD" value={num(h.total_donors)} note="Individual donors" />
          <HeaderKpi label="FB Followers" value={num(h.fb_followers)} note="Facebook" />
          <HeaderKpi label="Email Subscribers" value={num(h.email_subscribers)} note="All lists" />
          <HeaderKpi label="Surplus YTD" value={money(h.surplus_ytd)} note="Revenue − expenses" />
        </div>
      </header>

      <nav className="tabs">
        {Object.keys(TABS).map((t) => (
          <button key={t} className={'tab' + (t === tab ? ' active' : '')} onClick={() => setTab(t)}>{t}</button>
        ))}
      </nav>

      {tab !== 'Overview' && (
        <FilterBar brand={brand} range={range} onBrand={setBrand} onRange={setRange} />
      )}

      <main>
        {err ? <div className="loading">Couldn't load data: {err}</div>
          : !data ? <div className="loading">Loading the warehouse…</div>
          : TABS[tab](data, filters)}
      </main>

      <footer>Radio Milwaukee · Executive Dashboard · Live from the analytics warehouse · Board of Directors</footer>
    </div>
  )
}
