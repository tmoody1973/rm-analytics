import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '@clerk/react'

export function chatsUrl({ q, id } = {}) {
  if (id) return `/api/chats?id=${encodeURIComponent(id)}`
  if (q) return `/api/chats?q=${encodeURIComponent(q)}`
  return '/api/chats'
}

export function HistoryView() {
  const { getToken } = useAuth()
  const [q, setQ] = useState('')
  const [threads, setThreads] = useState([])
  const [active, setActive] = useState(null)   // {thread, messages}
  const [err, setErr] = useState(null)

  const authedFetch = useCallback(async (url) => {
    const token = await getToken()
    const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    return r.json()
  }, [getToken])

  useEffect(() => {
    authedFetch(chatsUrl({ q: q.trim() || undefined })).then(setThreads).catch((e) => setErr(e.message))
  }, [q, authedFetch])

  const open = (id) => authedFetch(chatsUrl({ id })).then(setActive).catch((e) => setErr(e.message))

  if (active) {
    return (
      <div className="history-detail">
        <button className="tab" onClick={() => setActive(null)}>← Back to history</button>
        <h3>{active.thread.title}</h3>
        <div className="history-meta">{active.thread.user_email} · {active.thread.updated_at}</div>
        {active.messages.map((m) => (
          <div key={m.seq} className={`chat-msg chat-${m.role}`}>
            <div className="chat-role">{m.role}</div>
            <div className="chat-content">{m.content}</div>
            {m.tool_calls ? (
              <details className="chat-sql"><summary>SQL it ran</summary>
                <pre>{JSON.stringify(m.tool_calls, null, 2)}</pre></details>
            ) : null}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="history">
      <input className="history-search" placeholder="Search past chats…"
             value={q} onChange={(e) => setQ(e.target.value)} />
      {err ? <div className="loading">Couldn't load history: {err}</div> : null}
      <ul className="history-list">
        {threads.map((t) => (
          <li key={t.thread_id} className="history-item" onClick={() => open(t.thread_id)}>
            <div className="history-title">{t.title}</div>
            <div className="history-sub">{t.user_email} · {t.updated_at} · {t.message_count ?? ''} msgs</div>
            {t.snippet ? <div className="history-snippet">…{t.snippet}…</div> : null}
          </li>
        ))}
        {threads.length === 0 && !err ? <li className="loading">No chats yet.</li> : null}
      </ul>
    </div>
  )
}
