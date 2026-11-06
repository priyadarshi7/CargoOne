import { CircleCheck, MapPin } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'

export interface Place { label: string; name: string; detail: string; lat: number; lng: number }
export type Pos = { lat: number; lng: number } | null

/** A place field with suggestions: type a few letters, pick the exact place, and its map position is kept with it.
 *  Typing again forgets the position (the text no longer matches it). If suggestions are unavailable the person can still type. */
export default function PlaceInput({ label, value, lat, lng, onChange, required, className = '' }: {
  label: string; value: string; lat: number | null; lng: number | null; onChange: (text: string, pos: Pos) => void; required?: boolean; className?: string
}) {
  const { t } = useI18n()
  const id = useId()
  const [results, setResults] = useState<Place[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [busy, setBusy] = useState(false)
  const [down, setDown] = useState(false)
  const latest = useRef(0) // answers to older keystrokes are ignored
  const timer = useRef<number | undefined>(undefined)
  const typed = useRef(false) // suggestions only after the person typed, not for a value that was filled in for them
  const picked = lat !== null && lng !== null

  useEffect(() => () => window.clearTimeout(timer.current), [])

  function search(text: string) {
    window.clearTimeout(timer.current)
    const q = text.trim()
    if (q.length < 3) { setResults([]); setOpen(false); setBusy(false); return }
    setBusy(true)
    timer.current = window.setTimeout(async () => {
      const mine = ++latest.current
      try {
        const found = await api<Place[]>(`/places/search?q=${encodeURIComponent(q)}`)
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

  function pick(p: Place) {
    latest.current++ // drop any answer still on its way
    typed.current = false
    onChange(p.label, { lat: p.lat, lng: p.lng })
    setOpen(false); setResults([])
  }

  function onKey(e: React.KeyboardEvent) {
    if (!open || results.length === 0) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => (i + 1) % results.length) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => (i <= 0 ? results.length - 1 : i - 1)) }
    else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); pick(results[active]) } // chooses the place, does not submit the form
    else if (e.key === 'Escape') { e.stopPropagation(); setOpen(false) }
  }

  const list = `${id}-list`
  return (
    <div className={`relative space-y-px text-sm ${className}`}>
      <label htmlFor={id} className="block font-medium leading-[18px]">{label}</label>
      <div className={`flex h-11 items-center gap-2 rounded-lg border bg-surface px-3 focus-within:border-ink ${picked ? 'border-ok' : 'border-line'}`}>
        <MapPin size={16} aria-hidden className={picked ? 'text-ok' : 'text-muted'} />
        <input id={id} role="combobox" aria-expanded={open} aria-controls={list} aria-autocomplete="list" aria-activedescendant={open && active >= 0 ? `${id}-o${active}` : undefined}
          autoComplete="off" required={required} minLength={2} maxLength={120} value={value}
          onChange={(e) => { typed.current = true; onChange(e.target.value, null); search(e.target.value) }}
          onKeyDown={onKey} onBlur={() => window.setTimeout(() => setOpen(false), 120)} onFocus={() => { if (typed.current && results.length) setOpen(true) }}
          className="h-full min-w-0 flex-1 bg-transparent outline-none" />
        {busy && <span aria-hidden className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line border-t-ink" />}
      </div>
      {open && results.length > 0 && (
        <ul id={list} role="listbox" aria-label={label} className="absolute left-0 right-0 z-30 mt-1 max-h-72 overflow-auto rounded-xl border border-line bg-surface py-1 shadow-lg">
          {results.map((p, i) => (
            <li key={`${p.lat},${p.lng}`} id={`${id}-o${i}`} role="option" aria-selected={i === active}
              onMouseDown={(e) => { e.preventDefault(); pick(p) }} onMouseEnter={() => setActive(i)}
              className={`flex cursor-pointer items-start gap-2.5 px-3 py-2 ${i === active ? 'bg-wash' : ''}`}>
              <MapPin size={15} aria-hidden className="mt-0.5 shrink-0 text-muted" />
              <span className="min-w-0"><span className="block truncate font-medium">{p.name}</span>{p.detail && <span className="block truncate text-xs text-muted">{p.detail}</span>}</span>
            </li>
          ))}
        </ul>
      )}
      <p aria-live="polite" className="min-h-4 pt-1 text-xs text-muted">
        {picked ? (
          <span className="inline-flex flex-wrap items-center gap-x-2 text-ok">
            <CircleCheck size={13} aria-hidden /> {t('place.saved')}
            <a href={`https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=16/${lat}/${lng}`} target="_blank" rel="noreferrer" className="underline underline-offset-2">{t('place.view')}</a>
          </span>
        ) : down ? t('place.down') : value.trim().length >= 3 && !busy ? t('place.pick') : t('place.hint')}
      </p>
    </div>
  )
}
