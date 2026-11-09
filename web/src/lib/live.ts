import { useEffect, useRef } from 'react'
import { authHeader, BASE } from './api'

/** Live updates. One WebSocket per open tab tells the screen WHICH kind of thing changed ("trips", "review", "billing", "requests",
 *  "expenses", "messages", "privacy", "setup"); the screen then asks the API for fresh data the usual way. No data travels on the socket.
 *  If it cannot connect (offline, a proxy that blocks it) nothing breaks: screens just keep their own refresh. */
const EVENT = 'cargoone:live'
const wsUrl = () => {
  const base = /^https?:/.test(BASE) ? BASE.replace(/^http/, 'ws') : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}${BASE}`
  return `${base}/ws`
}

/** Keeps the socket open for as long as someone is signed in (or a private link is in use). Returns a function that closes it. */
export function connectLive(auth: () => string | undefined): () => void {
  let ws: WebSocket | null = null
  let timer: number | undefined
  let tries = 0
  let stopped = false
  const open = () => {
    const a = auth()
    if (stopped || !a || !navigator.onLine) return
    ws = new WebSocket(wsUrl())
    ws.onopen = () => ws?.send(JSON.stringify({ auth: a }))
    ws.onmessage = (m) => {
      let msg: { t?: string; topics?: string[] }
      try { msg = JSON.parse(String(m.data)) } catch { return }
      if (msg.t === 'ready') { if (tries > 0) window.dispatchEvent(new CustomEvent(EVENT, { detail: ['*'] })); tries = 0 } // after a gap, look again at everything
      else if (msg.t === 'change' && msg.topics) window.dispatchEvent(new CustomEvent(EVENT, { detail: msg.topics }))
    }
    ws.onclose = (e) => {
      ws = null
      if (stopped || e.code === 4401) return // refused: not signed in
      tries += 1
      timer = window.setTimeout(open, Math.min(30_000, 1000 * 2 ** Math.min(tries, 5)))
    }
    ws.onerror = () => ws?.close()
  }
  const wake = () => { if (!ws && !stopped) { window.clearTimeout(timer); open() } }
  window.addEventListener('online', wake)
  document.addEventListener('visibilitychange', wake)
  open()
  return () => { stopped = true; window.clearTimeout(timer); window.removeEventListener('online', wake); document.removeEventListener('visibilitychange', wake); ws?.close() }
}

export const liveAuth = () => authHeader().Authorization

/** Runs `reload` when any of `topics` changes (at most once a moment, however many changes arrive). */
export function useLive(topics: readonly string[], reload: () => void): void {
  const fn = useRef(reload)
  fn.current = reload
  const key = topics.join(',')
  useEffect(() => {
    let timer: number | undefined
    const on = (e: Event) => {
      const got = (e as CustomEvent<string[]>).detail
      if (!got.includes('*') && !key.split(',').some((t) => got.includes(t))) return
      window.clearTimeout(timer)
      timer = window.setTimeout(() => fn.current(), 400)
    }
    window.addEventListener(EVENT, on)
    return () => { window.clearTimeout(timer); window.removeEventListener(EVENT, on) }
  }, [key])
}
