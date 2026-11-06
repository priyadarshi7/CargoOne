import { LocateFixed, MapPin, Search, X } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { useI18n } from '../lib/i18n'
import { loadGoogleMaps, type GMap } from '../lib/maps'
import { placesConfig, reversePlace, type Place, type Pos } from '../lib/places'
import { usePlaceSuggestions } from '../lib/usePlaceSuggestions'
import Suggestions from './Suggestions'

const DEPOT = { lat: 19.8762, lng: 75.3433 } // Chhatrapati Sambhajinagar: where the map opens when nothing is picked yet
const inIndia = (lat: number, lng: number) => lat >= 6 && lat <= 36 && lng >= 68 && lng <= 98
const near = (a: { lat: number; lng: number }, b: { lat: number; lng: number }) => Math.abs(a.lat - b.lat) < 0.0003 && Math.abs(a.lng - b.lng) < 0.0003 // about 30 m

type Spot = { label: string; name: string; detail: string }

/** Pick a place on a map the way delivery apps do: the pin stays in the middle, you move the map under it, and the address of the spot under
 *  the pin is shown and updates. Search jumps the map to a place; "use my location" jumps to where you are. Confirm saves the pin's exact position. */
export default function LocationPicker({ initial, onClose, onConfirm }: { initial: Pos; onClose: () => void; onConfirm: (label: string, pos: { lat: number; lng: number }) => void }) {
  const { t } = useI18n()
  const id = useId()
  const dialog = useRef<HTMLDialogElement>(null)
  const box = useRef<HTMLDivElement>(null)
  const map = useRef<GMap | null>(null)
  const s = usePlaceSuggestions()
  const [text, setText] = useState('')
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [google, setGoogle] = useState(false)
  const [moving, setMoving] = useState(false)
  const [finding, setFinding] = useState(false)
  const [spot, setSpot] = useState<Spot | null>(null)
  const [chosen, setChosen] = useState<Place | null>(null) // a searched place stays shown until the map is moved away from it
  const [note, setNote] = useState<string | null>(null)
  const chosenRef = useRef<Place | null>(null)
  const seq = useRef(0)
  const timer = useRef<number | undefined>(undefined)
  const setPicked = (p: Place | null) => { chosenRef.current = p; setChosen(p) }

  useEffect(() => { dialog.current?.showModal() }, [])

  function resolve() {
    const c = map.current?.getCenter()
    if (!c) return
    const lat = c.lat(), lng = c.lng()
    const keep = chosenRef.current
    if (keep && keep.lat !== null && keep.lng !== null && near({ lat, lng }, { lat: keep.lat, lng: keep.lng })) return // still on the searched place
    setPicked(null)
    if (!inIndia(lat, lng)) { setSpot(null); setNote(t('place.outside')); return }
    setNote(null); setFinding(true)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(async () => {
      const mine = ++seq.current
      try { const p = await reversePlace(lat, lng); if (mine === seq.current) setSpot({ label: p.label, name: p.name, detail: p.detail }) }
      catch { if (mine === seq.current) setSpot({ label: `${lat.toFixed(5)}, ${lng.toFixed(5)}`, name: `${lat.toFixed(5)}, ${lng.toFixed(5)}`, detail: '' }) } // the coordinates are still a usable answer
      finally { if (mine === seq.current) setFinding(false) }
    }, 350)
  }

  useEffect(() => {
    let dead = false
    const handles: { remove(): void }[] = []
    void (async () => {
      try {
        const cfg = await placesConfig()
        setGoogle(cfg.provider === 'google')
        if (!cfg.maps_key) throw new Error('no map key')
        const api = await loadGoogleMaps(cfg.maps_key)
        const { Map } = await api.importLibrary('maps')
        if (dead || !box.current) return
        const m = new Map(box.current, { center: initial ?? DEPOT, zoom: initial ? 17 : 13, disableDefaultUI: true, zoomControl: true, gestureHandling: 'greedy', clickableIcons: false, keyboardShortcuts: true })
        map.current = m
        handles.push(m.addListener('dragstart', () => setMoving(true)))
        handles.push(m.addListener('idle', () => { setMoving(false); resolve() }))
        setState('ready')
      } catch { if (!dead) setState('error') }
    })()
    return () => { dead = true; window.clearTimeout(timer.current); handles.forEach((h) => h.remove()); map.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function choose(p: Place) {
    const full = await s.pick(p)
    if (!full || full.lat === null || full.lng === null) return
    setText(full.label); setSpot(null); setNote(null); setPicked(full)
    map.current?.panTo({ lat: full.lat, lng: full.lng }); map.current?.setZoom(17)
  }

  function here() {
    setNote(null)
    if (!navigator.geolocation) return setNote(t('place.locDenied'))
    navigator.geolocation.getCurrentPosition(
      (pos) => { const p = { lat: pos.coords.latitude, lng: pos.coords.longitude }; if (!inIndia(p.lat, p.lng)) return setNote(t('place.outside')); setPicked(null); map.current?.panTo(p); map.current?.setZoom(17) },
      () => setNote(t('place.locDenied')), { enableHighAccuracy: true, timeout: 8000 })
  }

  const centre = () => { const c = map.current?.getCenter(); return c ? { lat: Math.round(c.lat() * 1e6) / 1e6, lng: Math.round(c.lng() * 1e6) / 1e6 } : null }
  const shown = chosen ? { name: chosen.name, detail: chosen.detail } : spot
  const canConfirm = !finding && !moving && (chosen !== null || (state === 'ready' && spot !== null && !note))

  function confirm() {
    if (chosen && chosen.lat !== null && chosen.lng !== null) return onConfirm(chosen.label, { lat: chosen.lat, lng: chosen.lng })
    const c = centre()
    if (c && spot && inIndia(c.lat, c.lng)) onConfirm(spot.label, c)
  }

  const list = `${id}-list`
  return (
    <dialog ref={dialog} onClose={onClose} aria-label={t('place.title')}
      className="m-0 h-dvh max-h-none w-screen max-w-none rounded-none border-0 bg-surface p-0 text-ink backdrop:bg-black/40 sm:m-auto sm:h-[min(46rem,92vh)] sm:w-[min(42rem,94vw)] sm:rounded-2xl sm:border sm:border-line">
      <div className="flex h-full flex-col">
        <header className="flex items-center justify-between gap-3 px-4 pb-2 pt-4">
          <h2 className="text-lg font-semibold">{t('place.title')}</h2>
          <button type="button" onClick={() => dialog.current?.close()} aria-label={t('common.close')} className="grid h-9 w-9 place-items-center rounded-lg text-muted hover:bg-wash hover:text-ink"><X size={20} aria-hidden /></button>
        </header>

        <div className="relative px-4 pb-3">
          <div className="flex h-11 items-center gap-2 rounded-lg border border-line bg-surface px-3 focus-within:border-ink">
            <Search size={16} aria-hidden className="text-muted" />
            <input role="combobox" aria-label={t('place.search')} aria-expanded={s.open} aria-controls={list} aria-autocomplete="list" aria-activedescendant={s.open && s.active >= 0 ? `${list}-o${s.active}` : undefined}
              autoComplete="off" placeholder={t('place.search')} value={text} maxLength={120}
              onChange={(e) => { setText(e.target.value); s.search(e.target.value) }}
              onKeyDown={(e) => s.onKey(e, (p) => void choose(p))} onBlur={() => window.setTimeout(() => s.setOpen(false), 120)}
              className="h-full min-w-0 flex-1 bg-transparent text-sm outline-none" />
            {s.busy && <span aria-hidden className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line border-t-ink" />}
          </div>
          {s.open && s.results.length > 0 && <div className="absolute left-4 right-4 top-12 z-30"><Suggestions id={list} label={t('place.search')} results={s.results} active={s.active} setActive={s.setActive} onPick={(p) => void choose(p)} google={google} /></div>}
          {s.down && <p className="pt-1 text-xs text-muted">{t('place.down')}</p>}
        </div>

        <div className="relative min-h-0 flex-1 bg-wash">
          <div ref={box} className="absolute inset-0" aria-label={t('place.mapLabel')} role="application" />
          {state === 'ready' && (
            <>
              <div aria-hidden className="pointer-events-none absolute left-1/2 top-1/2 z-10 -translate-x-1/2">
                <MapPin size={44} className={`-translate-y-full fill-ink text-surface drop-shadow-md transition-transform duration-150 ${moving ? '-translate-y-[calc(100%+10px)]' : ''}`} />
                <span className="absolute left-1/2 top-0 h-1.5 w-3 -translate-x-1/2 rounded-full bg-black/30" />
              </div>
              <button type="button" onClick={here} className="absolute bottom-3 left-3 z-10 inline-flex h-10 items-center gap-2 rounded-full border border-line bg-surface px-4 text-sm font-medium shadow-md hover:border-ink">
                <LocateFixed size={16} aria-hidden /> {t('place.current')}
              </button>
            </>
          )}
          {state === 'loading' && <p className="absolute inset-0 grid place-items-center text-sm text-muted">{t('place.mapLoading')}</p>}
          {state === 'error' && <p role="alert" className="absolute inset-0 grid place-items-center px-8 text-center text-sm text-bad">{t('place.mapDown')}</p>}
        </div>

        <footer className="space-y-3 border-t border-line px-4 py-4">
          <div className="min-h-12" aria-live="polite">
            {note ? <p className="text-sm font-medium text-warn">{note}</p>
              : finding || moving ? <p className="text-sm text-muted">{t('place.finding')}</p>
              : shown ? <><p className="font-semibold">{shown.name}</p>{shown.detail && <p className="text-sm text-muted">{shown.detail}</p>}</>
              : <p className="text-sm text-muted">{state === 'ready' ? t('place.hintPin') : ''}</p>}
          </div>
          <button type="button" disabled={!canConfirm} onClick={confirm} className="h-12 w-full rounded-xl bg-ink font-medium text-surface hover:opacity-90 disabled:opacity-40">{t('place.confirm')}</button>
        </footer>
      </div>
    </dialog>
  )
}
