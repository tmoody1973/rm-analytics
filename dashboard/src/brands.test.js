import { describe, it, expect } from 'vitest'
import { pageTitle } from './brands.js'

describe('pageTitle', () => {
  it('derives a readable headline from the last slug segment', () => {
    expect(pageTitle('/events-festivals/2026-02-19/summerfest-2026-lineup-daily-schedule'))
      .toBe('Summerfest 2026 Lineup Daily Schedule')
  })

  it('maps the site root to Homepage', () => {
    expect(pageTitle('/')).toBe('Homepage')
  })

  it('applies known casing fixups (88nine -> 88Nine)', () => {
    expect(pageTitle('/88nine-playlist')).toBe('88Nine Playlist')
  })

  it('handles a single-segment path', () => {
    expect(pageTitle('/contests')).toBe('Contests')
  })

  it('strips a query string / hash before deriving', () => {
    expect(pageTitle('/community-calendar?utm_source=x#top')).toBe('Community Calendar')
  })

  it('strips a leading ISO date inside the slug', () => {
    expect(pageTitle('/2026-06-19-summerfest-schedule')).toBe('Summerfest Schedule')
  })

  it('falls back to the previous segment when the last is a bare date', () => {
    expect(pageTitle('/blog/my-headline/2026-06-19')).toBe('My Headline')
  })

  it('is null-safe', () => {
    expect(pageTitle(null)).toBe('Untitled')
  })
})
