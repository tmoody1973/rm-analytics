import React, { useEffect, useState } from 'react'
import { QUESTION_METHOD, HELP_ROLES } from './help-guide.js'

// Click-to-copy question chip (mirrors Start Here's chips; reuses .ask-q styles).
function QChip({ q }) {
  const [copied, setCopied] = useState(false)
  const onClick = () => {
    try { navigator.clipboard && navigator.clipboard.writeText(q) } catch { /* clipboard blocked */ }
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

// The "How to ask" help guide. `roleId` selects which role section opens first
// (from a per-tab link); null opens on Board. Esc or click-outside closes.
export function HelpModal({ open, roleId, onClose }) {
  const [active, setActive] = useState(roleId || 'board')

  useEffect(() => { if (open && roleId) setActive(roleId) }, [open, roleId])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'          // lock background scroll
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [open, onClose])

  if (!open) return null
  const role = HELP_ROLES.find((r) => r.id === active) || HELP_ROLES[0]

  return (
    <div className="modal-overlay" role="presentation" onClick={onClose}>
      <div className="modal help-modal" role="dialog" aria-modal="true" aria-labelledby="help-title"
        onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <h2 id="help-title">How to ask the data analyst</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">×</button>
        </header>

        <div className="modal-body">
          {/* The method — how to build your own questions */}
          <section className="help-method">
            <p className="card-note">{QUESTION_METHOD.intro}</p>
            <div className="help-recipe">
              {QUESTION_METHOD.recipe.map((r) => (
                <div key={r.part} className="help-recipe-item">
                  <span className="help-recipe-part">{r.part}</span>
                  <span className="help-recipe-hint">{r.hint}</span>
                  <span className="help-recipe-eg">e.g. {r.eg}</span>
                </div>
              ))}
            </div>
            <p className="help-example">{QUESTION_METHOD.example}</p>
            <p className="help-example"><strong>Payoff:</strong> {QUESTION_METHOD.payoff}</p>
            <div className="help-habits">
              {QUESTION_METHOD.habits.map((h) => (
                <div key={h.title} className="help-habit">
                  <div className="help-habit-title">{h.title}</div>
                  <div className="help-habit-body">{h.body}</div>
                </div>
              ))}
            </div>
          </section>

          {/* Role selector */}
          <div className="subhead">Guides by role</div>
          <div className="help-roles">
            {HELP_ROLES.map((r) => (
              <button key={r.id} type="button"
                className={'help-role-pill' + (r.id === active ? ' active' : '')}
                onClick={() => setActive(r.id)}>{r.label}</button>
            ))}
          </div>

          {/* Selected role */}
          <section className="help-role-content" aria-live="polite">
            <p className="help-whofor">{role.whoFor}</p>

            <h4 className="help-h">The words that work</h4>
            <dl className="help-vocab">
              {role.vocab.map((v) => (
                <React.Fragment key={v.term}>
                  <dt>{v.term}</dt>
                  <dd>{v.def}</dd>
                </React.Fragment>
              ))}
            </dl>

            <h4 className="help-h">Questions to try — click to copy</h4>
            {Object.entries(role.ladder).map(([tier, qs]) => (
              <div key={tier} className="help-tier">
                <div className="help-tier-label">{tier}</div>
                {qs.map((q) => <QChip key={q} q={q} />)}
              </div>
            ))}

            <h4 className="help-h">Not tracked yet</h4>
            <ul className="start-list help-limits">
              {role.limits.map((l, i) => <li key={i}>{l}</li>)}
            </ul>
          </section>
        </div>
      </div>
    </div>
  )
}
