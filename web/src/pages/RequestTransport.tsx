import { CircleCheck, Truck } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../lib/api'
import { LANGUAGES, useI18n, type Lang } from '../lib/i18n'

const field = 'w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-base outline-none focus:border-accent'

export function PublicFrame({ children }: { children: ReactNode }) {
  const { lang, setLang } = useI18n()
  return (
    <div className="mx-auto min-h-full max-w-xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <span className="flex items-center gap-2 text-xl font-semibold"><Truck className="text-accent" aria-hidden /> CargoOne</span>
        <select aria-label="Language" value={lang} onChange={(e) => setLang(e.target.value as Lang)} className="rounded-lg border border-line bg-surface px-2 py-1.5 text-sm">
          {LANGUAGES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
      </div>
      {children}
    </div>
  )
}

const blank = { company_name: '', contact_name: '', phone: '', email: '', gstin: '', origin: '', destination: '', material: '', weight_tonnes: '', truck_type: '', pickup_date: '', notes: '', consent: false, website: '' }

/** The public page where a company asks for transport. No login. Hidden field `website` is a trap for bots. */
export default function RequestTransport() {
  const { t, lang } = useI18n()
  const [f, setF] = useState(blank)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<{ reference: string; status_url: string } | null>(null)
  const set = (k: keyof typeof blank) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const today = new Date().toISOString().slice(0, 10)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const clean = (v: string) => v.trim() || null
    try {
      const res = await api<{ reference: string; status_url: string }>('/public/requests', {
        method: 'POST',
        body: JSON.stringify({ ...f, language: lang, email: clean(f.email), gstin: clean(f.gstin), weight_tonnes: clean(f.weight_tonnes), truck_type: clean(f.truck_type), notes: clean(f.notes) }),
      })
      setDone(res)
    } catch (err) {
      setError(err instanceof ApiError ? (err.status === 429 ? t('req.rate') : `${t('req.fail')} ${err.message}`) : t('req.fail'))
    } finally { setBusy(false) }
  }

  if (done) {
    const path = done.status_url ? new URL(done.status_url).pathname : null
    return (
      <PublicFrame>
        <div className="space-y-4 text-center">
          <CircleCheck size={56} className="mx-auto text-ok" aria-hidden />
          <h1 className="text-2xl font-semibold">{t('req.thanks')}</h1>
          <p className="text-muted">{t('req.thanksBody', { ref: done.reference })}</p>
          {path && <Link to={path} className="inline-block rounded-lg bg-ink px-5 py-3 font-medium text-surface">{t('req.track')}</Link>}
          <div><button onClick={() => { setDone(null); setF(blank) }} className="text-sm underline">{t('req.again')}</button></div>
        </div>
      </PublicFrame>
    )
  }

  const label = (text: string, input: ReactNode, hint?: string) => (
    <label className="block space-y-1 text-sm"><span className="font-medium">{text}</span>{input}{hint && <span className="block text-xs text-muted">{hint}</span>}</label>
  )
  return (
    <PublicFrame>
      <h1 className="text-2xl font-semibold">{t('req.title')}</h1>
      <p className="mt-1 text-muted">{t('req.sub')}</p>
      <form onSubmit={(e) => void submit(e)} className="mt-6 space-y-4">
        {label(t('req.company'), <input className={field} required minLength={2} maxLength={160} value={f.company_name} onChange={set('company_name')} autoComplete="organization" />)}
        <div className="grid gap-4 sm:grid-cols-2">
          {label(t('req.contact'), <input className={field} required minLength={2} maxLength={120} value={f.contact_name} onChange={set('contact_name')} autoComplete="name" />)}
          {label(t('req.phone'), <input className={field} required inputMode="tel" value={f.phone} onChange={set('phone')} autoComplete="tel" />, t('req.phoneHint'))}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {label(t('req.email'), <input className={field} type="email" value={f.email} onChange={set('email')} autoComplete="email" />)}
          {label(t('req.gstin'), <input className={field} maxLength={15} value={f.gstin} onChange={(e) => setF({ ...f, gstin: e.target.value.toUpperCase() })} />)}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {label(t('req.origin'), <input className={field} required minLength={2} maxLength={120} value={f.origin} onChange={set('origin')} />)}
          {label(t('req.destination'), <input className={field} required minLength={2} maxLength={120} value={f.destination} onChange={set('destination')} />)}
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          {label(t('req.material'), <input className={field} required minLength={2} maxLength={160} value={f.material} onChange={set('material')} />)}
          {label(t('req.weight'), <input className={field} inputMode="decimal" value={f.weight_tonnes} onChange={set('weight_tonnes')} />)}
          {label(t('req.truck'), <input className={field} maxLength={60} value={f.truck_type} onChange={set('truck_type')} />)}
        </div>
        {label(t('req.pickup'), <input className={field} type="date" required min={today} value={f.pickup_date} onChange={set('pickup_date')} />)}
        {label(t('req.notes'), <textarea className={field} rows={3} maxLength={500} value={f.notes} onChange={set('notes')} />)}
        <div aria-hidden className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
          <label>Website <input tabIndex={-1} autoComplete="off" value={f.website} onChange={set('website')} /></label>
        </div>
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" required className="mt-1" checked={f.consent} onChange={(e) => setF({ ...f, consent: e.target.checked })} /> <span>{t('req.consent')}</span></label>
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
        <button disabled={busy} className="w-full rounded-lg bg-ink py-3 font-medium text-surface disabled:opacity-60">{busy ? t('req.sending') : t('req.submit')}</button>
      </form>
    </PublicFrame>
  )
}
