import { CircleCheck, Map as MapIcon, MapPin } from 'lucide-react'
import { useEffect, useId, useState } from 'react'
import { useI18n } from '../lib/i18n'
import { placesConfig, type Place, type PlacesConfig, type Pos } from '../lib/places'
import { usePlaceSuggestions } from '../lib/usePlaceSuggestions'
import LocationPicker from './LocationPicker'
import Suggestions from './Suggestions'

export type { Pos }

/** A place field with suggestions: type a few letters, pick the exact place, and its map position is kept with it. With Google set up there is
 *  also a "pick on map" button (a map with a fixed pin, like a delivery app). Typing again forgets the position (the text no longer matches it).
 *  If suggestions are unavailable the person can still type. */
export default function PlaceInput({ label, value, lat, lng, onChange, required, className = '' }: {
  label: string; value: string; lat: number | null; lng: number | null; onChange: (text: string, pos: Pos) => void; required?: boolean; className?: string
}) {
  const { t } = useI18n()
  const id = useId()
  const s = usePlaceSuggestions()
  const [cfg, setCfg] = useState<PlacesConfig>({ provider: 'photon', maps_key: null })
  const [mapOpen, setMapOpen] = useState(false)
  const picked = lat !== null && lng !== null
  useEffect(() => { void placesConfig().then(setCfg) }, [])

  async function choose(p: Place) {
    const full = await s.pick(p)
    if (full && full.lat !== null && full.lng !== null) onChange(full.label, { lat: full.lat, lng: full.lng })
  }

  const list = `${id}-list`
  return (
    <div className={`relative space-y-px text-sm ${className}`}>
      <label htmlFor={id} className="block font-medium leading-[18px]">{label}</label>
      <div className={`flex h-11 items-center gap-2 rounded-lg border bg-surface px-3 focus-within:border-ink ${picked ? 'border-ok' : 'border-line'}`}>
        <MapPin size={16} aria-hidden className={picked ? 'text-ok' : 'text-muted'} />
        <input id={id} role="combobox" aria-expanded={s.open} aria-controls={list} aria-autocomplete="list" aria-activedescendant={s.open && s.active >= 0 ? `${id}-o${s.active}` : undefined}
          autoComplete="off" required={required} minLength={2} maxLength={120} value={value}
          onChange={(e) => { onChange(e.target.value, null); s.search(e.target.value) }}
          onKeyDown={(e) => s.onKey(e, (p) => void choose(p))} onBlur={() => window.setTimeout(() => s.setOpen(false), 120)}
          className="h-full min-w-0 flex-1 bg-transparent outline-none" />
        {s.busy && <span aria-hidden className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line border-t-ink" />}
        {cfg.maps_key && (
          <button type="button" onClick={() => setMapOpen(true)} aria-label={t('place.map')} title={t('place.map')}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-muted hover:bg-wash hover:text-ink"><MapIcon size={17} aria-hidden /></button>
        )}
      </div>
      {s.open && s.results.length > 0 && <Suggestions id={list} label={label} results={s.results} active={s.active} setActive={s.setActive} onPick={(p) => void choose(p)} google={cfg.provider === 'google'} />}
      <p aria-live="polite" className="min-h-4 pt-1 text-xs text-muted">
        {picked ? (
          <span className="inline-flex flex-wrap items-center gap-x-2 text-ok">
            <CircleCheck size={13} aria-hidden /> {t('place.saved')}
            <a href={`https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=16/${lat}/${lng}`} target="_blank" rel="noreferrer" className="underline underline-offset-2">{t('place.view')}</a>
          </span>
        ) : s.down ? t('place.down') : value.trim().length >= 3 && !s.busy ? t('place.pick') : t('place.hint')}
      </p>
      {mapOpen && <LocationPicker initial={picked ? { lat: lat!, lng: lng! } : null} onClose={() => setMapOpen(false)} onConfirm={(text, pos) => { onChange(text, pos); setMapOpen(false) }} />}
    </div>
  )
}
