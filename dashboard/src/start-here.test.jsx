import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'
import { StartHere } from './start-here.jsx'

// Renders the component to static HTML (no browser/jsdom needed) and asserts the
// key sections + content are present. Guards against a render-time crash and
// confirms the board/staff guide, the assistant explainer, and the clickable
// example questions are all there.
describe('StartHere', () => {
  const html = renderToStaticMarkup(<StartHere />)

  it('renders without throwing and shows the guide heading', () => {
    expect(html).toContain('Start here')
  })

  it('lists the role tabs', () => {
    expect(html).toContain('Program Director')
    expect(html).toContain('Underwriting')
    expect(html).toContain('Finance / Exec')
  })

  it('explains the assistant and its privacy stance', () => {
    expect(html).toContain('Meet your data analyst')
    expect(html).toContain('de-identified')
  })

  it('includes clickable example questions with a Copy affordance', () => {
    expect(html).toContain('member retention')
    expect(html).toContain('engagement rate compare')
    expect(html.match(/>Copy</g)?.length || 0).toBeGreaterThanOrEqual(5)
  })
})
