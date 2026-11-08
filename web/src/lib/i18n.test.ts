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

import { en } from './i18n/en'
import { hi } from './i18n/hi'
import { mr } from './i18n/mr'

const holes = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',')

describe.each([['hi', hi], ['mr', mr]] as const)('%s dictionary', (_name, dict) => {
  it('only has keys that exist in English, with the same placeholders', () => {
    for (const [k, v] of Object.entries(dict)) {
      expect(k in en, `unknown key ${k}`).toBe(true)
      expect(holes(v as string), `placeholders differ in ${k}`).toBe(holes(en[k as keyof typeof en]))
    }
  })
  it('translates every English key', () => {
    // The AI benchmark screen (bench.*) is a QA tool for the ops head and stays in English; its title and menu entry are translated.
    const missing = Object.keys(en).filter((k) => !(k in dict) && !(k.startsWith('bench.') && k !== 'bench.title'))
    expect(missing).toEqual([])
  })
})
