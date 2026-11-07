import { describe, expect, it } from 'vitest'
import { hit } from './filters'

describe('hit', () => {
  it('matches everything when nothing is typed', () => {
    expect(hit('', 'anything')).toBe(true)
    expect(hit('   ', null, undefined)).toBe(true)
  })
  it('ignores case and word order, and needs every word', () => {
    expect(hit('PUNE ravi', 'Ravi Kumar', 'trip to Pune')).toBe(true)
    expect(hit('ravi nagpur', 'Ravi Kumar', 'trip to Pune')).toBe(false)
  })
  it('looks across numbers and skips empty fields', () => {
    expect(hit('4021', 'CO/26/00001', 4021, null)).toBe(true)
    expect(hit('null', 'a', null)).toBe(false)
  })
})
