import { afterEach, describe, expect, it, vi } from 'vitest'
import { resetClockForTests, serverNow, syncClock } from './serverClock'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); resetClockForTests() })

describe('server clock', () => {
  it('uses the phone clock, and says so, until the server has answered', () => {
    expect(serverNow().fromServer).toBe(false)
  })
  it('corrects a phone clock that is an hour fast by the server\'s Date header', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-06T10:00:00Z')) // the phone thinks it is 10:00
    vi.stubGlobal('fetch', async () => ({ ok: true, headers: new Headers({ date: new Date('2026-11-06T09:00:00Z').toUTCString() }) }))
    await syncClock()
    const { at, fromServer } = serverNow()
    expect(fromServer).toBe(true)
    expect(Math.abs(at.getTime() - new Date('2026-11-06T09:00:00.500Z').getTime())).toBeLessThan(1000) // the server says 09:00
  })
  it('falls back to the phone clock when the server cannot be reached', async () => {
    vi.stubGlobal('fetch', async () => { throw new Error('offline') })
    await syncClock()
    expect(serverNow().fromServer).toBe(false)
  })
})
