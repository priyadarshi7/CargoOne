import { describe, expect, it } from 'vitest'
import { stampSize, stampText } from './stamp'

describe('stampText', () => {
  it('prints the time in Indian time and the place', () => {
    const at = new Date('2026-11-06T09:02:00Z') // 14:32 in India
    expect(stampText(at, { lat: 21.1458, lng: 79.0882 })).toBe('CargoOne · 06 Nov 2026 14:32 IST · 21.14580N 79.08820E')
  })
  it('marks a time that came from the phone clock', () => {
    expect(stampText(new Date('2026-11-06T09:02:00Z'), null, false)).toContain('14:32 IST (phone clock)')
  })
  it('says so when there is no location, and uses S and W south and west of the equator and Greenwich', () => {
    const at = new Date('2026-11-06T09:02:00Z')
    expect(stampText(at, null)).toContain('location not available')
    expect(stampText(at, { lat: -1.5, lng: -3 })).toContain('1.50000S 3.00000W')
  })
})

describe('stampSize', () => {
  it('keeps the text inside the picture and legible', () => {
    const a = stampSize(1600, 4000) // text 40 px wide per 1 px of font at 100 -> 4000 means 40 per px
    expect(a.font).toBeLessThanOrEqual(48)
    expect(a.band).toBe(a.font * 2)
    expect(stampSize(300, 100000).font).toBe(11) // never tiny
  })
})
