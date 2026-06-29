import React, { useState } from 'react'
import { SectionTitle, ChartCard } from './components.jsx'

// "Start Here" — the default landing tab. Orients board members and staff to the
// dashboard and the AI analyst. Two depths on one page: a plain-language intro
// for board, then a by-department guide + example questions for staff.
//
// The example questions COPY to the clipboard (the chat configuration that could
// open the sidebar programmatically is scoped inside CopilotSidebar, not the app
// tree). One click copies the question; the reader opens the assistant (the chat
// button, lower-right) and pastes. Reliable and can't break the page.

const ROLE_TABS = [
  ['Overview', 'The whole organization at a glance — who we reach, revenue against plan, the health of our giving, and where we stand in the market.'],
  ['Program Director', "Who's listening, when, and whether they stay — across the broadcast signal and the streams."],
  ['Underwriting', 'The audience we can offer sponsors — by daypart, device, and demographic.'],
  ['Development', 'The health of our supporter base: how many give, whether they come back, and what they’re worth over time.'],
  ['Digital', 'How people find and move through our websites, and the content that brings them in.'],
  ['Social', 'How each brand grows and engages — and how our social compares to peer stations and competitors.'],
  ['Finance / Exec', "The money: what we've raised against budget, where it comes from, and what's left over."],
  ['History', 'Every past conversation with the analyst — searchable, so good answers don’t get lost.'],
]

const EXAMPLE_GROUPS = [
  {
    group: 'Membership & giving',
    qs: [
      'How are we tracking on member retention this year?',
      'Which months brought in the most new sustaining members?',
    ],
  },
  {
    group: 'Audience & programming',
    qs: [
      'What were our busiest streaming dayparts last month?',
      'How does 88Nine’s cume compare to earlier this year?',
    ],
  },
  {
    group: 'Digital & content',
    qs: [
      'What were our top web pages this week?',
      'Which newsletter topics drive the most opens?',
    ],
  },
  {
    group: 'Social & competitors',
    qs: [
      'How does our Instagram engagement rate compare to the public radio stations we track?',
      'What content themes are working best for the competitors we benchmark against?',
    ],
  },
  {
    group: 'Finance & the big picture',
    qs: [
      'How are we tracking against budget this year?',
      'What’s our revenue mix so far this year?',
    ],
  },
]

function QuestionButton({ q }) {
  const [copied, setCopied] = useState(false)
  const onClick = () => {
    try { navigator.clipboard && navigator.clipboard.writeText(q) } catch { /* clipboard blocked; the text is still selectable */ }
    setCopied(true)
    setTimeout(() => setCopied(false), 2200)
  }
  return (
    <button type="button" className="ask-q" onClick={onClick}
      title="Copy this question, then paste it into the assistant">
      <span className="ask-q-text">{q}</span>
      <span className={'ask-q-tag' + (copied ? ' copied' : '')}>{copied ? 'Copied ✓' : 'Copy'}</span>
    </button>
  )
}

export function StartHere() {
  return (
    <>
      <SectionTitle>Start here — your guide to the dashboard</SectionTitle>

      <p className="lede">
        This is Radio Milwaukee’s live analytics dashboard. Every number on it is pulled
        straight from our data warehouse and refreshed automatically — membership, audience,
        web, social, email, and finance, all in one place. You don’t need to be a “data
        person” to use it: the tabs across the top group everything by department, and the
        built-in assistant answers questions in plain English.
      </p>

      <ChartCard title="What’s in here">
        <p className="card-note">
          Use the tabs at the top of the page. Each one answers a different department’s
          questions:
        </p>
        <table className="rm">
          <tbody>
            {ROLE_TABS.map(([name, desc]) => (
              <tr key={name}>
                <td style={{ whiteSpace: 'nowrap', fontWeight: 600, verticalAlign: 'top', paddingRight: 18 }}>{name}</td>
                <td>{desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="note-flag">
          The brand filter and date range at the top of the page apply across the tabs, so you
          can narrow any view to 88Nine, HYFIN, 414 Music, or Rhythm Lab, over the window you care about.
        </div>
      </ChartCard>

      <ChartCard title="Meet your data analyst">
        <p className="card-note">
          The assistant is an AI data analyst that lives in this dashboard — open it with the
          chat button in the lower-right corner. Ask it anything about Radio Milwaukee’s data
          in plain language and it will find the answer, explain what it means, and tell you what
          to do about it.
        </p>
        <ul className="start-list">
          <li><strong>Every figure is live and cited.</strong> It pulls real numbers from the warehouse and names the source and time period — the chat and the dashboard never disagree.</li>
          <li><strong>It won’t make things up.</strong> If the warehouse can’t answer something, it says so plainly instead of guessing a number.</li>
          <li><strong>Donor privacy is built in.</strong> The giving data is de-identified — no names, no email addresses, no phone numbers — so the assistant can analyze trends but cannot reveal who any individual donor is.</li>
          <li><strong>Ask the way you’d ask a colleague.</strong> “How are we doing on member retention?” works better than trying to phrase a database query.</li>
        </ul>
      </ChartCard>

      <ChartCard title="Try asking">
        <p className="card-note">
          Click any question to copy it, then open the assistant (chat button, lower-right) and
          paste it in. These are good starting points — the assistant handles follow-ups, so
          keep the conversation going.
        </p>
        <div className="grid cols-2">
          {EXAMPLE_GROUPS.map(({ group, qs }) => (
            <div key={group} className="ask-group">
              <div className="ask-group-title">{group}</div>
              {qs.map((q) => <QuestionButton key={q} q={q} />)}
            </div>
          ))}
        </div>
      </ChartCard>

      <ChartCard title="Good to know">
        <ul className="start-list">
          <li><strong>The data refreshes on its own.</strong> Streaming updates daily, social weekly, and most other sources every day — you’re always looking at recent numbers, not a stale export.</li>
          <li><strong>Some sources are still being connected.</strong> If a tab says something isn’t tracked yet, that’s honest — we’re still wiring a few pipelines, and the assistant will tell you when it can’t answer.</li>
          <li><strong>Small samples deserve caution.</strong> For ratings and brand-new data, the assistant flags when a single number is directional rather than definitive.</li>
          <li><strong>Need access for a colleague, or have a question about a number?</strong> Contact Tarik — access is limited to Radio Milwaukee staff and board.</li>
        </ul>
      </ChartCard>
    </>
  )
}
