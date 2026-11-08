import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { db } from './db'
import { markServer } from './online'

export async function readCache<T>(key: string): Promise<{ value: T; savedAt: number } | null> {
  try {
    const row = await (await db()).get('kv', key)
    return row ? { value: row.value as T, savedAt: row.savedAt } : null
  } catch { return null }
}

export async function writeCache(key: string, value: unknown): Promise<void> {
  try { await (await db()).put('kv', { key, value, savedAt: Date.now() }) } catch { /* storage full or blocked: the screen still works online */ }
}

export async function clearCache(): Promise<void> {
  try { await (await db()).clear('kv') } catch { /* nothing to clear */ }
}

/** Reads `path` from the API and keeps the last good answer on the phone. With no network the saved answer is shown
 *  (`stale` is true) instead of an error. Saved answers are per signed-in person (`scope`), never shared between drivers. */
export function useCachedApi<T>(path: string, scope: string, refreshKey: unknown = 0): { data: T | null; stale: boolean; loaded: boolean; reload: () => void; mutate: (fn: (d: T) => T) => void } {
  const [data, setData] = useState<T | null>(null)
  const [stale, setStale] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [tick, setTick] = useState(0)
  const key = `${scope}:${path}`
  const changed = useRef(0) // counts the changes made on the phone (mutate): an answer from the server that was asked for before one is out of date

  useEffect(() => {
    let alive = true
    void (async () => {
      const saved = await readCache<T>(key)
      if (alive && saved) { setData(saved.value); setLoaded(true) } // show the phone's copy at once, then refresh it
      const asked = changed.current
      try {
        const fresh = await api<T>(path)
        if (!alive) return
        if (asked !== changed.current) return // the driver did something while this was on its way (start, reached): it would flip the screen back; the next look has it
        markServer(true)
        setData(fresh); setStale(false); setLoaded(true)
        void writeCache(key, fresh)
      } catch (e) {
        if (!alive) return
        if (e instanceof ApiError) { markServer(true); setLoaded(true); return } // the server answered with an error: not an offline case
        markServer(false)
        setStale(saved !== null); setLoaded(true)
      }
    })()
    return () => { alive = false }
  }, [key, path, refreshKey, tick])

  const mutate = useCallback((fn: (d: T) => T) => { // change what is shown and saved at once (an action taken with no network)
    changed.current += 1
    setData((d) => { if (d === null) return d; const next = fn(d); void writeCache(key, next); return next })
  }, [key])
  return { data, stale, loaded, reload: useCallback(() => setTick((n) => n + 1), []), mutate }
}
