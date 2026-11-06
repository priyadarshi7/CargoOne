import { BASE } from './api'

/** The server's clock, as the phone sees it. A driver's phone clock can be wrong (or set wrong on purpose), so the time printed on a delivery
 *  photo is the server's time: the app learns how far its own clock is from the server's and corrects for it.
 *  Without a recent answer (offline since the app opened) it falls back to the phone clock and says so. */
let offsetMs: number | null = null
let syncedAt = 0
const FRESH_MS = 10 * 60_000

/** Asks the server for the time (the Date header of any answer, with the trip there and back split in half). Never throws or waits long. */
export async function syncClock(timeoutMs = 2500): Promise<void> {
  if (offsetMs !== null && Date.now() - syncedAt < FRESH_MS) return
  try {
    const t0 = Date.now()
    const res = await fetch(`${BASE}/health`, { cache: 'no-store', signal: AbortSignal.timeout(timeoutMs) })
    const t1 = Date.now()
    const header = res.headers.get('date')
    if (!res.ok || !header) return
    offsetMs = new Date(header).getTime() + 500 /* the header has whole seconds */ - (t0 + t1) / 2
    syncedAt = t1
  } catch { /* offline or slow: the phone clock is used */ }
}

/** The server's time now, and whether it really is the server's (false: the phone's own clock). */
export function serverNow(): { at: Date; fromServer: boolean } {
  return offsetMs === null ? { at: new Date(), fromServer: false } : { at: new Date(Date.now() + offsetMs), fromServer: true }
}

export function resetClockForTests() { offsetMs = null; syncedAt = 0 }
