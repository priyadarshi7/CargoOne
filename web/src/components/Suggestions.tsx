import { MapPin } from 'lucide-react'
import type { Place } from '../lib/places'
import { useI18n } from '../lib/i18n'

/** The list under a place box. Google asks to be credited when its suggestions are shown without a Google map. */
export default function Suggestions({ id, label, results, active, setActive, onPick, google }: {
  id: string; label: string; results: Place[]; active: number; setActive: (i: number) => void; onPick: (p: Place) => void; google: boolean
}) {
  const { t } = useI18n()
  return (
    <ul id={id} role="listbox" aria-label={label} className="absolute left-0 right-0 z-30 mt-1 max-h-72 overflow-auto rounded-xl border border-line bg-surface py-1 shadow-lg">
      {results.map((p, i) => (
        <li key={p.id ?? `${p.lat},${p.lng}`} id={`${id}-o${i}`} role="option" aria-selected={i === active}
          onMouseDown={(e) => { e.preventDefault(); onPick(p) }} onMouseEnter={() => setActive(i)}
          className={`flex cursor-pointer items-start gap-2.5 px-3 py-2 ${i === active ? 'bg-wash' : ''}`}>
          <MapPin size={15} aria-hidden className="mt-0.5 shrink-0 text-muted" />
          <span className="min-w-0"><span className="block truncate font-medium">{p.name}</span>{p.detail && <span className="block truncate text-xs text-muted">{p.detail}</span>}</span>
        </li>
      ))}
      {google && <li role="presentation" className="px-3 pb-1 pt-1.5 text-right text-[11px] text-muted">{t('place.google')}</li>}
    </ul>
  )
}
