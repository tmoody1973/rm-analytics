// Content for the "How to ask" help guide (rendered by help-modal.jsx).
// Two parts: a shared METHOD for building your own questions, and a per-role
// guide (who it's for, the words that work, a ladder of example questions, and
// an honest "not tracked yet" note). Grounded in what the warehouse actually holds.

export const QUESTION_METHOD = {
  intro:
    'The analyst answers plain-language questions and cites every number. You don’t ' +
    'need to know SQL or which tool holds which metric — but a little structure gets ' +
    'you a sharper answer. Build a question from these parts:',
  recipe: [
    { part: 'Metric', hint: 'What you’re measuring.', eg: 'members, cume, revenue, engagement rate' },
    { part: 'Segment', hint: 'Which slice.', eg: 'a brand (88Nine, HYFIN), a daypart, a channel, a donor tier, a region' },
    { part: 'Timeframe', hint: 'When.', eg: 'this month, year-over-year, since the spring pledge drive' },
    { part: 'Comparison', hint: 'Against what.', eg: 'last year, budget, our goal, a peer station' },
  ],
  example:
    'Put together: “How does HYFIN’s streaming cume this month compare to last year?” ' +
    '= metric (cume) + segment (HYFIN) + timeframe (this month) + comparison (last year).',
  payoff:
    'End with the payoff so you get a decision, not just a number: add “…and is that ' +
    'good?” or “…what should we do about it?”',
  habits: [
    {
      title: 'Start from the decision',
      body: 'Work backwards from the call you need to make. “Should we renew this sponsor?” ' +
        'becomes “What audience can we show them by daypart and device?”',
    },
    {
      title: 'Keep the thread going',
      body: 'The best answers come from follow-ups. Drill down (“which daypart?”), compare ' +
        '(“vs 88Nine?”), or challenge it (“is that a real change or a small-sample blip?”).',
    },
    {
      title: 'Ask it to check itself',
      body: 'If you’re not sure the data exists, just ask — “do we track that?” The analyst ' +
        'will look and tell you plainly instead of guessing. It won’t make up a number.',
    },
  ],
}

export const HELP_ROLES = [
  {
    id: 'board',
    label: 'Board & Executive',
    tabKey: 'Overview',
    whoFor:
      'The whole-organization view: are we healthy, on plan, and reaching people. ' +
      'Lead with the “so what,” keep it tight, and connect dollars to mission.',
    vocab: [
      { term: 'Revenue vs budget', def: 'Actual money raised against the fiscal-year plan.' },
      { term: 'Surplus / deficit YTD', def: 'Revenue minus expenses, year-to-date.' },
      { term: 'LUNA', def: 'Liquid Unrestricted Net Assets — roughly, months of operating cash on hand.' },
      { term: 'Cume', def: 'Cumulative unique audience — how many distinct people we reach.' },
      { term: 'Sustainers', def: 'Recurring monthly donors — the stable base of giving.' },
      { term: 'AQH share', def: 'Nielsen — our slice of Milwaukee’s broadcast listening.' },
    ],
    ladder: {
      Starter: [
        'How are we tracking against budget this fiscal year?',
        'Are we running a surplus or deficit year-to-date?',
      ],
      Compare: [
        'How does our revenue this year compare to the same point last year?',
        'How does our Nielsen standing in Milwaukee compare to last book?',
      ],
      Diagnose: [
        'Our surplus is shrinking — is that expenses running ahead of budget, or revenue behind?',
        'Are we keeping last year’s donors, or leaking them?',
      ],
      Strategic: [
        'If you had to tell the board one thing going well and one to watch, what would they be?',
        'Which brand is reaching the most new people this year, and what’s it costing us?',
      ],
    },
    limits: [
      'Only the current fiscal year of finance is loaded — no multi-year financial trends yet.',
      'Donor identities aren’t in the warehouse (de-identified by design). No names, ever.',
    ],
  },
  {
    id: 'program_director',
    label: 'Program Director',
    tabKey: 'Program Director',
    whoFor:
      'Who’s listening, when, and whether they’re staying — across the broadcast signal ' +
      'and the streams. Content, dayparts, and tune-out.',
    vocab: [
      { term: 'Cume', def: 'Unique listeners (streaming or broadcast). Non-additive — don’t sum days.' },
      { term: 'TLH', def: 'Total Listening Hours — the volume of listening.' },
      { term: 'Sessions (SS)', def: 'Stream starts — how many times people tuned in.' },
      { term: 'TSL', def: 'Time Spent Listening — how long a listener stays.' },
      { term: 'AAS', def: 'Average Active Sessions — concurrent listeners.' },
      { term: 'Daypart', def: 'Standard time blocks (mornings, middays, etc.).' },
      { term: 'AQH', def: 'Nielsen Average Quarter-Hour — broadcast audience in a 15-min window.' },
    ],
    ladder: {
      Starter: [
        'What were 88Nine’s busiest streaming dayparts last month?',
        'How many people are we reaching on HYFIN right now?',
      ],
      Compare: [
        'How does 88Nine’s cume this month compare to earlier this year?',
        'How does HYFIN compare to 88Nine on time spent listening?',
      ],
      Diagnose: [
        'Sessions are up but listening hours are flat — are people tuning in and bouncing?',
        'When in the day do we lose the most listeners?',
      ],
      Strategic: [
        'Where’s the best daypart to add or move a show, based on where listening peaks?',
        'Is our streaming growth coming from more people, or the same people listening more?',
      ],
    },
    limits: [
      'Streaming data starts Jan 2024 (Rhythm Lab from Nov 2025). Nielsen is 88Nine + HYFIN only.',
      'Song- or show-level listening isn’t in the warehouse yet — this is stream/daypart level.',
    ],
  },
  {
    id: 'underwriting',
    label: 'Underwriting',
    tabKey: 'Underwriting',
    whoFor:
      'The audience we can offer sponsors — by daypart, device, and demographic — plus ' +
      'underwriting revenue. The “what can we sell” view.',
    vocab: [
      { term: 'AAS by daypart', def: 'Concurrent listeners by time block — sellable inventory.' },
      { term: 'Device split', def: 'What listeners use (mobile, smart speaker, desktop, car).' },
      { term: 'Cume', def: 'Unique reach — the size of the audience you’re offering.' },
      { term: 'Nielsen demos', def: 'Broadcast audience by age / gender / ethnic composition.' },
      { term: 'Underwriting revenue', def: 'Corporate support dollars (in the finance data).' },
    ],
    ladder: {
      Starter: [
        'What’s our average concurrent audience by daypart on 88Nine?',
        'What devices do our streaming listeners use most?',
      ],
      Compare: [
        'How does HYFIN’s daytime audience compare to 88Nine’s for a sponsor?',
        'How is underwriting revenue tracking versus last year?',
      ],
      Diagnose: [
        'Which dayparts have the most unsold-feeling capacity — high audience we’re under-using?',
        'Are smart-speaker listeners a big enough segment to pitch to a voice-first sponsor?',
      ],
      Strategic: [
        'If a healthcare sponsor wants weekday mornings, what audience and demos can we show them?',
        'What’s the strongest audience story we can tell an advertiser about HYFIN right now?',
      ],
    },
    limits: [
      'The sales pipeline, individual sponsors, and contracts aren’t loaded yet — only underwriting *revenue* (as a finance category).',
      'Ad-delivery / spot-level data (Triton a2x) is out of scope for now.',
    ],
  },
  {
    id: 'development',
    label: 'Development',
    tabKey: 'Development',
    whoFor:
      'The health of our supporter base: how many give, whether they come back, and what ' +
      'they’re worth over time. Org-wide — the brand filter doesn’t apply here.',
    vocab: [
      { term: 'Active donors', def: 'Supporters who gave in the last 12 months.' },
      { term: 'Sustainers', def: 'Recurring monthly donors; the sustainer ratio is a stability signal.' },
      { term: 'MRR', def: 'Monthly Recurring Revenue from sustaining gifts.' },
      { term: 'Retention', def: 'Share of last year’s donors who gave again.' },
      { term: 'Lifetime giving (LTV)', def: 'Total a donor has given over time.' },
      { term: 'Designation', def: 'What a gift was for (membership, foundations, etc.).' },
    ],
    ladder: {
      Starter: [
        'How many active donors do we have, and what’s their total lifetime giving?',
        'How many sustaining members do we have, and what’s the recurring revenue?',
      ],
      Compare: [
        'How are we tracking on member retention this year versus last?',
        'Are we acquiring new donors faster than we’re losing them?',
      ],
      Diagnose: [
        'Is our giving concentrated in a few major gifts, or broad across the base?',
        'Which months brought in the most new sustainers — and what was happening then?',
      ],
      Strategic: [
        'Where are our donors, and where might there be room to grow?',
        'If we wanted to lift retention 5 points, which donor segment should we focus on?',
      ],
    },
    limits: [
      'No donor identities — the data is de-identified (no names, emails, or phones). Patterns and de-identified records only.',
      'Giving data goes back to 2023.',
    ],
  },
  {
    id: 'digital',
    label: 'Digital & Marketing',
    tabKey: 'Digital',
    whoFor:
      'How people find and move through our sites, and the content and email that bring ' +
      'them in. Web + newsletter performance.',
    vocab: [
      { term: 'Active users', def: 'Distinct people visiting the site.' },
      { term: 'Pageviews', def: 'Pages viewed; pages-per-user shows how deep they go.' },
      { term: 'Channels', def: 'How people arrive — search, direct, social, email, referral.' },
      { term: 'Engagement time', def: 'How long visitors stay / average session duration.' },
      { term: 'Open & click rate', def: 'Newsletter performance metrics.' },
      { term: 'Topic tags', def: 'What each newsletter was about (auto-tagged), for correlation.' },
    ],
    ladder: {
      Starter: [
        'What web pages are drawing the most people right now?',
        'How is website traffic trending this year?',
      ],
      Compare: [
        'How do people find us — search, social, email, direct — and how has that shifted?',
        'How do this month’s newsletter open rates compare to last month’s?',
      ],
      Diagnose: [
        'A page spiked in views but low engagement time — was it a one-off or worth doubling down on?',
        'Which newsletter topics actually drive opens, and which don’t?',
      ],
      Strategic: [
        'Which content and channels bring the most engaged visitors — where should we invest?',
        'What should our content team make more of, based on what’s working?',
      ],
    },
    limits: [
      'Web covers radiomilwaukee.org and HYFIN’s site. Page titles are derived from URLs.',
      'App-download and podcast metrics aren’t fully wired in yet.',
    ],
  },
  {
    id: 'social',
    label: 'Social',
    tabKey: 'Social',
    whoFor:
      'How each brand’s audience is growing and engaging — and how our social compares to ' +
      'peer stations and competitors. Lead with engagement rate, not follower count.',
    vocab: [
      { term: 'Engagement rate', def: 'Interactions ÷ followers — comparable across account sizes.' },
      { term: 'Reach', def: 'Unique people who saw a post.' },
      { term: 'Owned vs competitor', def: 'Our accounts vs the watchlist we benchmark against.' },
      { term: 'Content theme', def: 'What a post is about (event promo, local artist, etc.), auto-tagged.' },
      { term: 'Followers', def: 'Audience size — a vanity number; use engagement rate to compare.' },
    ],
    ladder: {
      Starter: [
        'How is Instagram engagement trending for 88Nine and HYFIN?',
        'What are our best-performing posts lately?',
      ],
      Compare: [
        'How does our Instagram engagement rate compare to the public radio stations we track?',
        'Are we punching above or below our weight versus peers our size?',
      ],
      Diagnose: [
        'A small account beats us on engagement rate — what are they doing that we aren’t?',
        'Which content themes get the best engagement for us versus competitors?',
      ],
      Strategic: [
        'Based on what’s working across the accounts we track, what should we post more of?',
        'What content is working for competitors that we aren’t doing at all?',
      ],
    },
    limits: [
      'Competitive social covers a recent, rolling window of the watchlist — not deep history.',
      'Paid social (ad spend / ROAS) isn’t loaded yet; this is organic + competitive benchmarking.',
    ],
  },
  {
    id: 'finance',
    label: 'Finance & Exec',
    tabKey: 'Finance / Exec',
    whoFor:
      'The money: what we’ve raised against budget, where it comes from, and what’s left ' +
      'over. Revenue mix and financial health.',
    vocab: [
      { term: 'Revenue Actual / Budget YTD', def: 'Money raised vs the fiscal-year plan, to date.' },
      { term: '% to annual budget', def: 'How far along we are toward the full-year revenue goal.' },
      { term: 'Revenue mix', def: 'Underwriting vs individual giving vs foundations.' },
      { term: 'Expenses Actual / Budget YTD', def: 'Spending against plan.' },
      { term: 'Surplus / deficit YTD', def: 'Revenue minus expenses so far.' },
      { term: 'Cash balance / LUNA', def: 'Cash on hand; LUNA ≈ months of operating cash.' },
    ],
    ladder: {
      Starter: [
        'How are we tracking against budget this fiscal year?',
        'What’s our revenue mix so far this year?',
      ],
      Compare: [
        'How does revenue this month compare to budget, and to the same month last year?',
        'Are expenses on budget, or running ahead?',
      ],
      Diagnose: [
        'We’re behind on revenue — is it underwriting, individual giving, or foundations lagging?',
        'What’s driving the change in surplus this month?',
      ],
      Strategic: [
        'If foundation revenue is front-loaded, what does the rest of the year need to look like?',
        'Which revenue line has the most upside for the back half of the year?',
      ],
    },
    limits: [
      'Only the current fiscal year is loaded — no multi-year finance trends yet.',
      'Underwriting *pipeline*, events ticketing, and the grants pipeline aren’t loaded yet.',
    ],
  },
]

// Map a dashboard tab name -> a help role id, for the per-tab "How to ask" link.
export const TAB_TO_ROLE = HELP_ROLES.reduce((m, r) => {
  m[r.tabKey] = r.id
  return m
}, {})
