import { describe, expect, it } from 'vitest'
import { digitsOf, MOBILE, phoneProblem, showPhone } from './phone'

describe('phone', () => {
  it('turns every way of writing a number into the plain 10 digits', () => {
    for (const t of ['9876543210', '98765 43210', '+91 98765 43210', '+91-98765-43210', '09876543210', '(98765) 43210']) expect(digitsOf(t)).toBe('9876543210')
  })
  it('does not eat digits that are really part of the number while it is being typed', () => {
    expect(digitsOf('91')).toBe('91')
    expect(digitsOf('919')).toBe('919')
    expect(digitsOf('0')).toBe('0')
  })
  it('never lets more than 10 digits in', () => {
    expect(digitsOf('987654321012345')).toBe('9876543210')
  })
  it('says what is wrong as soon as it is known', () => {
    expect(phoneProblem('')).toBeNull()
    expect(phoneProblem('5')).toBe('start') // Indian mobiles start 6 to 9: wrong from the first digit
    expect(phoneProblem('98765')).toBe('short')
    expect(phoneProblem('9876543210')).toBeNull()
  })
  it('matches the server rule', () => {
    expect(MOBILE.test('9876543210')).toBe(true)
    expect(MOBILE.test('5876543210')).toBe(false)
    expect(MOBILE.test('987654321')).toBe(false)
  })
  it('shows a stored number in two groups', () => {
    expect(showPhone('9876543210')).toBe('98765 43210')
    expect(showPhone('123')).toBe('123')
  })
})
