import { openDB, type DBSchema, type IDBPDatabase } from 'idb'

/** One small IndexedDB for everything a driver's phone keeps so the app still works with no network:
 *  `kv` holds the last answer of each read (trips, messages, expenses), `outbox` holds actions waiting to be sent. */
export type OutboxKind = 'start' | 'expense'
export interface OutboxItem {
  id: string // doubles as the server's idempotency key, so a retry never saves twice
  kind: OutboxKind
  data: Record<string, string>
  photo?: Blob
  createdAt: number
  attempts: number
  status: 'queued' | 'failed'
  error?: string
}

interface Schema extends DBSchema {
  kv: { key: string; value: { key: string; value: unknown; savedAt: number } }
  outbox: { key: string; value: OutboxItem; indexes: { 'by-created': number } }
}

let dbp: Promise<IDBPDatabase<Schema>> | null = null
export const db = () =>
  (dbp ??= openDB<Schema>('cargoone-offline', 1, {
    upgrade(d) {
      d.createObjectStore('kv', { keyPath: 'key' })
      d.createObjectStore('outbox', { keyPath: 'id' }).createIndex('by-created', 'createdAt')
    },
  }))

export const newId = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('')
