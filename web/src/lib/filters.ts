import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

/** Every word typed must appear somewhere in the row's text (any order, any case), so "ravi pune" finds Ravi's trip to Pune. */
export function hit(query: string, ...fields: (string | number | null | undefined)[]): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (words.length === 0) return true
  const text = fields.filter((f) => f !== null && f !== undefined).join(' ').toLowerCase()
  return words.every((w) => text.includes(w))
}

/** Filter choices kept in the page's address (?q=pune&pod=needs_review), so a filtered list survives a refresh and a link can open it already filtered.
 *  A value equal to its default is left out of the address. */
export function useFilters<T extends Record<string, string>>(defaults: T) {
  const [params, setParams] = useSearchParams()
  const values = Object.fromEntries(Object.keys(defaults).map((k) => [k, params.get(k) ?? defaults[k]])) as T
  const set = useCallback((key: keyof T & string, value: string) => {
    setParams((p) => { const n = new URLSearchParams(p); if (value === defaults[key] || value === '') n.delete(key); else n.set(key, value); return n }, { replace: true })
  }, [setParams, defaults])
  const clear = useCallback(() => {
    setParams((p) => { const n = new URLSearchParams(p); Object.keys(defaults).forEach((k) => n.delete(k)); return n }, { replace: true })
  }, [setParams, defaults])
  const active = Object.keys(defaults).some((k) => values[k] !== defaults[k])
  return { values, set, clear, active }
}
