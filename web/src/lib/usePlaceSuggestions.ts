import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { newSession, placeDetails, searchPlaces, type Place } from './places'

/** The typing-and-choosing logic shared by the place field and the map picker: debounced search, answers to older keystrokes ignored,
 *  keyboard control, and (for Google suggestions, which have no position yet) fetching the position when one is picked. */
export function usePlaceSuggestions() {
  const [results, setResults] = useState<Place[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [busy, setBusy] = useState(false)
  const [down, setDown] = useState(false)
  const latest = useRef(0)
  const timer = useRef<number | undefined>(undefined)
  const session = useRef(newSession())
  useEffect(() => () => window.clearTimeout(timer.current), [])

  function search(text: string) {
    window.clearTimeout(timer.current)
    const q = text.trim()
    if (q.length < 3) { latest.current++; setResults([]); setOpen(false); setBusy(false); return }
    setBusy(true)
    timer.current = window.setTimeout(async () => {
      const mine = ++latest.current
      try {
        const found = await searchPlaces(q, session.current)
        if (mine !== latest.current) return
        setResults(found); setDown(false); setActive(found.length ? 0 : -1); setOpen(true)
      } catch {
        if (mine !== latest.current) return
        setResults([]); setDown(true); setOpen(false)
      } finally {
        if (mine === latest.current) setBusy(false)
      }
    }, 350)
  }

  /** The chosen place with its position, or null when the position could not be fetched (the person can still type the place). */
  async function pick(p: Place): Promise<Place | null> {
    latest.current++ // drop any answer still on its way
    setOpen(false); setResults([])
    let full = p
    if (p.lat === null || p.lng === null) {
      if (!p.id) return null
      setBusy(true)
      try { full = await placeDetails(p.id, session.current); setDown(false) } catch { setDown(true); return null } finally { setBusy(false) }
    }
    session.current = newSession() // the search-then-pick is over: the next search is a new session
    return full
  }

  function onKey(e: KeyboardEvent, choose: (p: Place) => void) {
    if (!open || results.length === 0) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => (i + 1) % results.length) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => (i <= 0 ? results.length - 1 : i - 1)) }
    else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); choose(results[active]) } // chooses the place, does not submit the form
    else if (e.key === 'Escape') { e.stopPropagation(); setOpen(false) }
  }

  return { results, open, setOpen, active, setActive, busy, down, search, pick, onKey }
}
