import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'
import { HelpModal } from './help-modal.jsx'
import { HELP_ROLES } from './help-guide.js'

describe('HelpModal', () => {
  it('renders nothing when closed', () => {
    expect(renderToStaticMarkup(<HelpModal open={false} roleId={null} onClose={() => {}} />)).toBe('')
  })

  const html = renderToStaticMarkup(<HelpModal open roleId="development" onClose={() => {}} />)

  it('shows the title and the question-building method', () => {
    expect(html).toContain('How to ask the data analyst')
    for (const part of ['Metric', 'Segment', 'Timeframe', 'Comparison']) expect(html).toContain(part)
  })

  it('lists every role and opens on the requested one', () => {
    // renderToStaticMarkup HTML-escapes '&' (e.g. "Board & Executive" -> "&amp;").
    for (const r of HELP_ROLES) expect(html).toContain(r.label.replace(/&/g, '&amp;'))
    // Development section content is present (opened via roleId).
    expect(html).toContain('active donors')            // a Development vocab term
    expect(html).toContain('member retention')          // a Development example question
  })

  it('renders click-to-copy question chips and the tiered ladder', () => {
    for (const tier of ['Starter', 'Compare', 'Diagnose', 'Strategic']) expect(html).toContain(tier)
    expect(html.match(/>Copy</g)?.length || 0).toBeGreaterThanOrEqual(5)
  })

  it('includes an honest "not tracked yet" section', () => {
    expect(html).toContain('Not tracked yet')
  })
})
