import { useEffect, useState } from 'react'
import { authHeader, BASE, getActiveLink } from '../api'
import { db, newId, type OutboxItem, type OutboxKind } from './db'

/** Actions a driver takes with no network (start a trip, say the truck has reached, report a delay, add an expense) are saved on the phone first and sent in order
 *  when the network returns. The server treats a repeated start as a no-op and a repeated expense id as the same expense,
 *  so a retry can never do the action twice. */
let last = 0
const stamp = () => (last = Math.max(Date.now(), last + 1))
const listeners = new Set<() => void>()
const changed = () => listeners.forEach((f) => f())

export async function enqueueAction(kind: OutboxKind, data: Record<string, string>, photo?: Blob, id = newId()): Promise<OutboxItem> {
  const item: OutboxItem = { id, kind, data, photo, createdAt: stamp(), attempts: 0, status: 'queued', link: getActiveLink() ?? undefined }
  await (await db()).put('outbox', item)
  changed()
  return item
}

export const listOutbox = async () => (await db()).getAllFromIndex('outbox', 'by-created')

export class PermanentSendError extends Error {}

/** Sends one saved action. A 4xx the server will never change its mind about is permanent; network errors, 5xx and an
 *  expired login (401) leave the action saved. */
export async function sendItem(item: OutboxItem): Promise<void> {
  const auth: Record<string, string> = item.link ? { Authorization: `Link ${item.link}` } : authHeader()
  let res: Response
  if (item.kind === 'start') {
    res = await fetch(`${BASE}/trips/${encodeURIComponent(item.data.trip_id)}/start`, { method: 'POST', headers: auth })
  } else if (item.kind === 'arrived') {
    res = await fetch(`${BASE}/trips/${encodeURIComponent(item.data.trip_id)}/arrived`, { method: 'POST', headers: auth })
  } else if (item.kind === 'road') {
    const { trip_id, kind, reason, minutes } = item.data
    res = await fetch(`${BASE}/trips/${encodeURIComponent(trip_id)}/events`, { method: 'POST', headers: { ...auth, 'Content-Type': 'application/json' }, body: JSON.stringify({ kind, reason, minutes: minutes ? Number(minutes) : null }) })
  } else if (item.kind === 'loaded') {
    const form = new FormData()
    if (item.photo) form.set('file', item.photo, 'loaded.webp')
    res = await fetch(`${BASE}/trips/${encodeURIComponent(item.data.trip_id)}/loaded`, { method: 'POST', body: form, headers: auth })
  } else {
    const form = new FormData()
    for (const [k, v] of Object.entries(item.data)) form.set(k, v)
    form.set('client_expense_id', item.id)
    if (item.photo) form.set('photo', item.photo, 'bill.webp')
    res = await fetch(`${BASE}/expenses`, { method: 'POST', body: form, headers: auth })
  }
  if (res.ok) return
  if (res.status === 401 && item.link) throw new PermanentSendError('The link has expired. Ask the office for a new one.') // a revoked link will not come back
  if (res.status >= 500 || res.status === 401 || res.status === 408 || res.status === 429) throw new Error(`temporary ${res.status}`)
  const detail = await res.json().then((j) => (typeof j.detail === 'string' ? j.detail : res.statusText)).catch(() => res.statusText)
  throw new PermanentSendError(detail)
}

type Sender = (item: OutboxItem) => Promise<void>
let running: Promise<void> | null = null

/** Oldest first; stops at the first network failure so the order is kept. Concurrent calls share one run. */
export function flushOutbox(send: Sender = sendItem): Promise<void> {
  return (running ??= run(send).finally(() => { running = null; changed() }))
}

async function run(send: Sender): Promise<void> {
  const d = await db()
  for (const item of await listOutbox()) {
    if (item.status !== 'queued') continue
    try {
      await send(item)
      await d.delete('outbox', item.id)
    } catch (e) {
      if (e instanceof PermanentSendError) { await d.put('outbox', { ...item, attempts: item.attempts + 1, status: 'failed', error: e.message }); continue }
      await d.put('outbox', { ...item, attempts: item.attempts + 1 })
      return
    }
  }
}

export const dismissFailed = async (id: string) => { await (await db()).delete('outbox', id); changed() }

/** How many actions are waiting on this phone, and keeps them draining: at start, when the network returns, when the app
 *  comes back to the front, and every 30 seconds. */
export function useOutbox(): { waiting: number; failed: OutboxItem[]; syncNow: () => Promise<void> } {
  const [state, setState] = useState<{ waiting: number; failed: OutboxItem[] }>({ waiting: 0, failed: [] })
  useEffect(() => {
    let alive = true
    const read = async () => {
      const all = await listOutbox()
      if (alive) setState({ waiting: all.filter((i) => i.status === 'queued').length, failed: all.filter((i) => i.status === 'failed') })
    }
    const sync = async () => { await flushOutbox().catch(() => undefined); await read() }
    listeners.add(read)
    void sync()
    window.addEventListener('online', sync)
    const onVisible = () => { if (document.visibilityState === 'visible') void sync() }
    document.addEventListener('visibilitychange', onVisible)
    const timer = setInterval(sync, 30_000)
    return () => { alive = false; listeners.delete(read); window.removeEventListener('online', sync); document.removeEventListener('visibilitychange', onVisible); clearInterval(timer) }
  }, [])
  return { ...state, syncNow: async () => { await flushOutbox().catch(() => undefined) } }
}
