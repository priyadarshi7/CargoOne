import { Search, X } from 'lucide-react'
import { useI18n } from '../lib/i18n'

export interface FilterSelect { key: string; label: string; value: string; options: [value: string, label: string][]; onChange: (v: string) => void }

/** One row above a list: a search box, any drop-downs, how many rows are showing, and a Clear that appears once something is filtered. */
export function FilterBar({ q, onQ, placeholder, selects = [], shown, total, active, onClear }: {
  q: string; onQ: (v: string) => void; placeholder: string; selects?: FilterSelect[]; shown: number; total: number; active: boolean; onClear: () => void
}) {
  const { t } = useI18n()
  const box = 'h-9 rounded-lg border border-line bg-surface px-3 text-sm outline-none focus:border-accent'
  return (
    <div role="search" className="flex flex-wrap items-center gap-2">
      <label className="relative min-w-52 flex-1 sm:max-w-sm">
        <Search size={16} aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
        <input type="search" value={q} onChange={(e) => onQ(e.target.value)} placeholder={placeholder} aria-label={t('filter.search')} className={`${box} w-full pl-9`} />
      </label>
      {selects.map((s) => (
        <select key={s.key} value={s.value} onChange={(e) => s.onChange(e.target.value)} aria-label={s.label} className={box}>
          {s.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      ))}
      <span className="text-sm text-muted" aria-live="polite">{t('filter.showing', { a: shown, b: total })}</span>
      {active && <button type="button" onClick={onClear} className="inline-flex h-9 items-center gap-1 rounded-lg px-2.5 text-sm font-medium text-accent hover:bg-accent-soft"><X size={14} aria-hidden /> {t('filter.clear')}</button>}
    </div>
  )
}

/** Shown in place of a table or list when the filters leave nothing. */
export function NoMatch({ onClear }: { onClear: () => void }) {
  const { t } = useI18n()
  return <p className="rounded-xl border border-line px-4 py-8 text-center text-muted">{t('filter.none')} <button type="button" onClick={onClear} className="font-medium text-accent underline">{t('filter.clear')}</button></p>
}
