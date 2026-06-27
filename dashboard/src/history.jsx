import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import { useAuth, useUser } from '@clerk/react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// ── pure helpers (unit-tested) ───────────────────────────────────────────────

export function toolCallSummary(toolCalls) {
  // Returns [{name, args}] from either the AG-UI shape or a simple {name,args} shape.
  return (toolCalls || []).map((c) => {
    const name = c.function?.name ?? c.name ?? 'tool'
    let parsed = c.function?.arguments ?? c.args ?? {}
    if (typeof parsed === 'string') { try { parsed = JSON.parse(parsed) } catch { /* keep string */ } }
    return { name, args: parsed }
  })
}

export function chatsUrl({ q, id } = {}) {
  if (id) return `/api/chats?id=${encodeURIComponent(id)}`
  if (q) return `/api/chats?q=${encodeURIComponent(q)}`
  return '/api/chats'
}

const DAY = 86400000

// Which recency bucket a timestamp falls in, relative to `nowMs`.
export function timeBucket(iso, nowMs = Date.now()) {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return 'Earlier'
  const now = new Date(nowMs)
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  if (t >= startOfToday) return 'Today'
  if (t >= startOfToday - DAY) return 'Yesterday'
  if (t >= startOfToday - 6 * DAY) return 'This Week'
  return 'Earlier'
}

// Friendly, compact timestamp for the card meta line.
export function formatWhen(iso, nowMs = Date.now()) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const bucket = timeBucket(iso, nowMs)
  const time = d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  if (bucket === 'Today') return time
  if (bucket === 'Yesterday') return `Yesterday · ${time}`
  if (bucket === 'This Week') return `${d.toLocaleDateString(undefined, { weekday: 'short' })} · ${time}`
  const sameYear = d.getFullYear() === new Date(nowMs).getFullYear()
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', ...(sameYear ? {} : { year: 'numeric' }) })
}

const BUCKET_ORDER = ['Today', 'Yesterday', 'This Week', 'Earlier']

export function groupThreads(threads, nowMs = Date.now()) {
  const by = new Map()
  for (const t of threads) {
    const b = timeBucket(t.updated_at, nowMs)
    if (!by.has(b)) by.set(b, [])
    by.get(b).push(t)
  }
  return BUCKET_ORDER.filter((b) => by.has(b)).map((label) => ({ label, items: by.get(label) }))
}

const nameOf = (email) => (email ? email.split('@')[0] : 'someone')
const initialOf = (email) => (email ? email.trim()[0].toUpperCase() : '?')

// ── transcript ───────────────────────────────────────────────────────────────

function Transcript({ messages }) {
  return (
    <div className="ch-thread">
      {messages.map((m) => (
        <div key={m.seq} className={`ch-row ch-${m.role === 'assistant' ? 'assistant' : 'user'}`}>
          <div className="ch-who">{m.role === 'assistant' ? 'Analyst' : 'You'}</div>
          <div className="ch-bubble">
            {m.role === 'assistant'
              ? <div className="ch-md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content || ''}</ReactMarkdown></div>
              : <div className="ch-text">{m.content}</div>}
            {m.tool_calls ? (
              <details className="ch-sql">
                <summary>SQL it ran</summary>
                {toolCallSummary(m.tool_calls).map((tc, i) => (
                  <div className="ch-sql-item" key={i}>
                    <span className="ch-sql-name">{tc.name}</span>
                    <pre>{tc.args.sql ? tc.args.sql : JSON.stringify(tc.args, null, 2)}</pre>
                  </div>
                ))}
              </details>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── one collapsible chat card ────────────────────────────────────────────────

function ChatCard({ thread, nowMs, open, onToggle, detail, loading }) {
  return (
    <div className={'ch-card' + (open ? ' open' : '')}>
      <button className="ch-head" onClick={onToggle} aria-expanded={open}>
        <span className="ch-avatar" title={thread.user_email}>{initialOf(thread.user_email)}</span>
        <span className="ch-main">
          <span className="ch-title">{thread.title || 'Untitled chat'}</span>
          <span className="ch-meta">
            {nameOf(thread.user_email)} · {formatWhen(thread.updated_at, nowMs)}
            {thread.message_count ? ` · ${thread.message_count} msg${thread.message_count === 1 ? '' : 's'}` : ''}
          </span>
          {!open && thread.snippet ? <span className="ch-snippet">…{thread.snippet}…</span> : null}
        </span>
        <span className="ch-chev" aria-hidden>›</span>
      </button>
      {open ? (
        <div className="ch-body">
          {loading ? <div className="ch-loading">Loading conversation…</div>
            : detail ? <Transcript messages={detail.messages} />
            : <div className="ch-loading">Couldn't load this conversation.</div>}
        </div>
      ) : null}
    </div>
  )
}

// ── the History view ─────────────────────────────────────────────────────────

export function HistoryView() {
  const { getToken } = useAuth()
  const { user } = useUser()
  const myEmail = user?.primaryEmailAddress?.emailAddress?.toLowerCase() || null

  const [q, setQ] = useState('')
  const [scope, setScope] = useState('mine')          // 'mine' | 'everyone'
  const [threads, setThreads] = useState([])
  const [openId, setOpenId] = useState(null)
  const [details, setDetails] = useState({})          // thread_id -> {thread, messages}
  const [loadingId, setLoadingId] = useState(null)
  const [err, setErr] = useState(null)
  const nowMs = useRef(Date.now()).current

  const authedFetch = useCallback(async (url) => {
    const token = await getToken()
    const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    return r.json()
  }, [getToken])

  // Load / search threads (debounced on the query).
  useEffect(() => {
    let alive = true
    const run = () => authedFetch(chatsUrl({ q: q.trim() || undefined }))
      .then((rows) => { if (alive) { setThreads(Array.isArray(rows) ? rows : []); setErr(null) } })
      .catch((e) => { if (alive) setErr(e.message) })
    const h = setTimeout(run, q ? 220 : 0)
    return () => { alive = false; clearTimeout(h) }
  }, [q, authedFetch])

  const visible = useMemo(() => {
    if (scope === 'mine' && myEmail) {
      return threads.filter((t) => (t.user_email || '').toLowerCase() === myEmail)
    }
    return threads
  }, [threads, scope, myEmail])

  const groups = useMemo(() => groupThreads(visible, nowMs), [visible, nowMs])

  const toggle = (t) => {
    const id = t.thread_id
    if (openId === id) { setOpenId(null); return }
    setOpenId(id)
    if (!details[id]) {
      setLoadingId(id)
      authedFetch(chatsUrl({ id }))
        .then((d) => setDetails((m) => ({ ...m, [id]: d })))
        .catch(() => {})
        .finally(() => setLoadingId((cur) => (cur === id ? null : cur)))
    }
  }

  return (
    <div className="hist">
      <div className="hist-bar">
        <div className="hist-search">
          <span className="hist-search-ico" aria-hidden>⌕</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search past chats…" />
        </div>
        <div className="hist-scope" role="tablist" aria-label="Whose chats">
          <button className={scope === 'mine' ? 'on' : ''} onClick={() => setScope('mine')}>Mine</button>
          <button className={scope === 'everyone' ? 'on' : ''} onClick={() => setScope('everyone')}>Everyone</button>
        </div>
      </div>

      {err ? <div className="hist-empty">Couldn't load history: {err}</div> : null}

      {!err && visible.length === 0 ? (
        <div className="hist-empty">
          <div className="hist-empty-mark">⌕</div>
          {q ? <p>No chats match “{q}”.</p>
            : scope === 'mine'
              ? <p>You haven’t asked the assistant anything yet. Open the chat and ask a question — it’ll show up here.</p>
              : <p>No chats yet.</p>}
        </div>
      ) : null}

      {groups.map((g) => (
        <section className="hist-group" key={g.label}>
          <h3 className="hist-group-title">{g.label}<span>{g.items.length}</span></h3>
          <div className="hist-cards">
            {g.items.map((t) => (
              <ChatCard
                key={t.thread_id}
                thread={t}
                nowMs={nowMs}
                open={openId === t.thread_id}
                onToggle={() => toggle(t)}
                detail={details[t.thread_id]}
                loading={loadingId === t.thread_id}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
