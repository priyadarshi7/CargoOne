import { useEffect, useState } from 'react'
import { api } from './api'

/** How many messages the driver has not opened yet. Checked when the app opens, when it comes back to the front, and every minute.
 *  With no network it keeps the last number it knew. */
export function useUnread(enabled = true): number {
  const [n, setN] = useState(0)
  useEffect(() => {
    if (!enabled) return
    let alive = true
    const load = () => api<{ unread: number }>('/notifications/mine?limit=1').then((r) => { if (alive) setN(r.unread) }).catch(() => undefined)
    void load()
    const every = window.setInterval(load, 60_000)
    const onVisible = () => { if (document.visibilityState === 'visible') void load() }
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('cargoone:messages-read', load)
    return () => { alive = false; window.clearInterval(every); document.removeEventListener('visibilitychange', onVisible); window.removeEventListener('cargoone:messages-read', load) }
  }, [enabled])
  return n
}
