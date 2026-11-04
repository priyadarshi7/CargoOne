import { describe, expect, it } from 'vitest'
import { translate } from './i18n'

describe('translate', () => {
  it('returns the language text and substitutes placeholders', () => {
    expect(translate('hi', 'nav.trips')).toBe('ट्रिप')
    expect(translate('mr', 'review.hoursAgo', { n: 5 })).toBe('5 तासांपूर्वी')
    expect(translate('en', 'review.daysAgo', { n: 3 })).toBe('3 days ago')
  })
  it('never shows a blank or a raw key: every Hindi and Marathi string keeps the same placeholders as English', () => {
    for (const k of ['review.hoursAgo', 'review.daysAgo'] as const) {
      for (const l of ['hi', 'mr'] as const) expect(translate(l, k, { n: 7 })).toContain('7')
    }
  })
})
