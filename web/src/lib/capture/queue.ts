import { openDB, type DBSchema, type IDBPDatabase } from 'idb'

/** Offline-first upload queue persisted in IndexedDB. A photo is safe on the device the instant it is queued;
 *  uploads retry whenever the network returns. `id` doubles as the server idempotency key, so retries
 *  can never create duplicate submissions. */

export interface UploadResult {
  submission_id: string
  decision: 'verified' | 'needs_review' | 'retake_requested'
  reasons: string[]
  voice: string
  attempt: number
  retakes_left: number
  duplicate: boolean
}

export interface QueuedPod {
  id: string
  tripId: string
  blob: Blob
  capturedAt: string
  lat: number | null
  lng: number | null
  createdAt: number
  attempts: number
  status: 'queued' | 'done' | 'failed'
  result?: UploadResult
  error?: string
}

interface Schema extends DBSchema {
  pods: { key: string; value: QueuedPod; indexes: { 'by-created': number } }
}

/** Thrown by the uploader for failures that will never succeed on retry (e.g. 409, 413, 415, 422). */
export class PermanentUploadError extends Error {}

let dbp: Promise<IDBPDatabase<Schema>> | null = null
const db = () =>
  (dbp ??= openDB<Schema>('cargoone-capture', 1, {
    upgrade(d) {
      d.createObjectStore('pods', { keyPath: 'id' }).createIndex('by-created', 'createdAt')
    },
  }))

const DONE_TTL_MS = 24 * 3600 * 1000

// Strictly increasing, so FIFO order holds even for photos queued in the same millisecond.
let lastStamp = 0
const nextStamp = () => (lastStamp = Math.max(Date.now(), lastStamp + 1))

export async function enqueue(p: Pick<QueuedPod, 'tripId' | 'blob' | 'capturedAt' | 'lat' | 'lng'>): Promise<QueuedPod> {
  const item: QueuedPod = { ...p, id: crypto.randomUUID().replaceAll('-', ''), createdAt: nextStamp(), attempts: 0, status: 'queued' }
  await (await db()).put('pods', item)
  return item
}

export const getItem = async (id: string) => (await db()).get('pods', id)
export const listAll = async () => (await db()).getAllFromIndex('pods', 'by-created')
export const acknowledge = async (id: string) => (await db()).delete('pods', id)
export const pendingCount = async () => (await listAll()).filter((i) => i.status === 'queued').length

type Uploader = (item: QueuedPod) => Promise<UploadResult>
let flushing: Promise<void> | null = null

/** Uploads queued items oldest-first. Stops at the first network failure (still offline).
 *  Concurrent calls share one run, so a photo is never sent twice in parallel. */
export function flush(upload: Uploader): Promise<void> {
  return (flushing ??= run(upload).finally(() => (flushing = null)))
}

async function run(upload: Uploader): Promise<void> {
  const d = await db()
  for (const item of await listAll()) {
    if (item.status === 'done' && Date.now() - item.createdAt > DONE_TTL_MS) await d.delete('pods', item.id)
    if (item.status !== 'queued') continue
    try {
      const result = await upload(item)
      await d.put('pods', { ...item, attempts: item.attempts + 1, status: 'done', result })
    } catch (e) {
      if (e instanceof PermanentUploadError) {
        await d.put('pods', { ...item, attempts: item.attempts + 1, status: 'failed', error: e.message })
        continue
      }
      await d.put('pods', { ...item, attempts: item.attempts + 1 })
      return // offline or server down: keep order, try again later
    }
  }
}
