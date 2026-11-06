import { ArrowLeft, CircleCheck, Truck } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import PhoneInput from '../components/PhoneInput'
import PlaceInput from '../components/PlaceInput'
import { Link } from 'react-router-dom'
import { ThemeToggle } from '../components/ThemeToggle'
import { api, ApiError } from '../lib/api'
import { LANGUAGES, useI18n, type Lang } from '../lib/i18n'

const field = 'h-11 w-full rounded-lg border border-line bg-surface px-3.5 text-base outline-none focus:border-ink'
const QUICK_TRUCKS = ['Open body', 'Container', 'Trailer', 'Tanker']

/** The frame of every public page (request form, request status, onboarding): brand, back link, language. `wide` is for the form with its side panel. */
export function PublicFrame({ children, wide }: { children: ReactNode; wide?: boolean }) {
  const { t, lang, setLang } = useI18n()
  return (
    <div className="min-h-full">
      <header className="border-b border-line">
        <div className={`mx-auto flex h-16 items-center gap-3 px-5 sm:px-8 ${wide ? 'max-w-5xl' : 'max-w-2xl'}`}>
          <Link to="/" className="flex items-center gap-2.5 text-lg font-semibold tracking-tight">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-ink text-surface"><Truck size={16} aria-hidden /></span> CargoOne
          </Link>
          <Link to="/" className="ml-2 hidden items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-muted hover:text-ink sm:inline-flex"><ArrowLeft size={15} aria-hidden /> {t('req.back')}</Link>
          <div className="ml-auto flex items-center gap-2">
            <select aria-label="Language" value={lang} onChange={(e) => setLang(e.target.value as Lang)} className="h-9 rounded-lg border border-line bg-surface px-2 text-sm text-muted">
              {LANGUAGES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
            </select>
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className={`mx-auto px-5 py-10 sm:px-8 sm:py-14 ${wide ? 'max-w-5xl' : 'max-w-2xl'}`}>{children}</main>
    </div>
  )
}

const blank = { company_name: '', contact_name: '', phone: '', email: '', gstin: '', origin: '', destination: '', origin_lat: null as number | null, origin_lng: null as number | null, destination_lat: null as number | null, destination_lng: null as number | null, material: '', weight_tonnes: '', truck_type: '', pickup_date: '', notes: '', consent: false, website: '' }

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
        <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-8 text-center">
          <span className="grid h-16 w-16 place-items-center rounded-full bg-ok-soft text-ok"><CircleCheck size={34} aria-hidden /></span>
          <h1 className="text-3xl font-semibold tracking-tight">{t('req.thanks')}</h1>
          <p className="text-muted">{t('req.thanksBody', { ref: done.reference })}</p>
          {path && <Link to={path} className="inline-flex h-12 items-center rounded-xl bg-ink px-7 font-medium text-surface hover:opacity-90">{t('req.track')}</Link>}
          <button onClick={() => { setDone(null); setF(blank) }} className="text-sm text-muted underline underline-offset-2">{t('req.again')}</button>
        </div>
      </PublicFrame>
    )
  }

  const label = (text: string, input: ReactNode, hint?: string) => (
    <label className="block space-y-1.5 text-sm"><span className="font-medium">{text}</span>{input}{hint && <span className="block text-xs text-muted">{hint}</span>}</label>
  )
  const next = ['n1', 'n2', 'n3'] as const
  return (
    <PublicFrame wide>
      <div className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_300px]">
        <form onSubmit={(e) => void submit(e)} className="max-w-2xl space-y-8">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t('req.title')}</h1>
            <p className="mt-2 text-muted">{t('req.sub')}</p>
            <p className="mt-2 text-sm text-muted">{t('req.haveLogin')} <Link to="/login" className="font-medium text-ink underline underline-offset-2">{t('req.signIn')}</Link></p>
          </div>

          <fieldset className="space-y-4">
            <legend className="mb-1 text-base font-semibold">1. {t('req.s1')}</legend>
            {label(t('req.company'), <input className={field} required minLength={2} maxLength={160} value={f.company_name} onChange={set('company_name')} autoComplete="organization" />)}
            <div className="grid gap-4 sm:grid-cols-2">
              {label(t('req.contact'), <input className={field} required minLength={2} maxLength={120} value={f.contact_name} onChange={set('contact_name')} autoComplete="name" />)}
              <PhoneInput label={t('req.phone')} hint={t('req.phoneHint')} required value={f.phone} onChange={(v) => setF({ ...f, phone: v })} />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {label(t('req.email'), <input className={field} type="email" value={f.email} onChange={set('email')} autoComplete="email" />)}
              {label(t('req.gstin'), <input className={`${field} font-mono`} maxLength={15} value={f.gstin} onChange={(e) => setF({ ...f, gstin: e.target.value.toUpperCase() })} />)}
            </div>
          </fieldset>

          <hr className="border-line" />

          <fieldset className="space-y-4">
            <legend className="mb-1 text-base font-semibold">2. {t('req.s2')}</legend>
            <div className="grid gap-4 sm:grid-cols-2">
              <PlaceInput label={t('req.origin')} required value={f.origin} lat={f.origin_lat} lng={f.origin_lng} onChange={(text, pos) => setF({ ...f, origin: text, origin_lat: pos?.lat ?? null, origin_lng: pos?.lng ?? null })} />
              <PlaceInput label={t('req.destination')} required value={f.destination} lat={f.destination_lat} lng={f.destination_lng} onChange={(text, pos) => setF({ ...f, destination: text, destination_lat: pos?.lat ?? null, destination_lng: pos?.lng ?? null })} />
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              {label(t('req.material'), <input className={field} required minLength={2} maxLength={160} value={f.material} onChange={set('material')} />)}
              {label(t('req.weight'), <input className={field} inputMode="decimal" value={f.weight_tonnes} onChange={set('weight_tonnes')} />)}
              {label(t('req.pickup'), <input className={field} type="date" required min={today} value={f.pickup_date} onChange={set('pickup_date')} />)}
            </div>
            <div className="space-y-2">
              {label(t('req.truck'), <input className={field} maxLength={60} value={f.truck_type} onChange={set('truck_type')} />)}
              <div className="flex flex-wrap gap-2" role="group" aria-label={t('req.quick')}>
                {QUICK_TRUCKS.map((x) => (
                  <button key={x} type="button" aria-pressed={f.truck_type === x} onClick={() => setF({ ...f, truck_type: f.truck_type === x ? '' : x })}
                    className={`h-9 rounded-full border px-3.5 text-sm ${f.truck_type === x ? 'border-ink bg-ink text-surface' : 'border-line text-muted hover:border-ink hover:text-ink'}`}>{x}</button>
                ))}
              </div>
            </div>
            {label(t('req.notes'), <textarea className={`${field} h-auto py-3`} rows={3} maxLength={500} value={f.notes} onChange={set('notes')} />)}
          </fieldset>

          <div aria-hidden className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
            <label>Website <input tabIndex={-1} autoComplete="off" value={f.website} onChange={set('website')} /></label>
          </div>
          <hr className="border-line" />
          <label className="flex items-start gap-3 text-sm text-muted"><input type="checkbox" required className="mt-0.5 h-5 w-5 accent-[var(--color-ink)]" checked={f.consent} onChange={(e) => setF({ ...f, consent: e.target.checked })} /> <span>{t('req.consent')}</span></label>
          {error && <p role="alert" className="rounded-lg bg-bad-soft px-3 py-2 text-sm text-bad">{error}</p>}
          <div className="flex flex-wrap items-center gap-4">
            <button disabled={busy} className="h-12 rounded-xl bg-ink px-8 text-base font-medium text-surface hover:opacity-90 disabled:opacity-60">{busy ? t('req.sending') : t('req.submit')}</button>
            <span className="text-sm text-muted">{t('req.after')}</span>
          </div>
        </form>

        <aside className="space-y-4 lg:sticky lg:top-8 lg:self-start">
          <div className="space-y-5 rounded-2xl border border-line bg-wash p-6">
            <h2 className="font-semibold">{t('req.next')}</h2>
            <ol className="space-y-4">
              {next.map((k, i) => (
                <li key={k} className="flex gap-3">
                  <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-line bg-surface font-mono text-xs text-muted">{i + 1}</span>
                  <span><span className="block text-sm font-medium">{t(`req.${k}.t`)}</span><span className="block text-sm text-muted">{t(`req.${k}.b`)}</span></span>
                </li>
              ))}
            </ol>
          </div>
          <p className="px-1 text-xs text-muted">{t('req.privacy')}</p>
        </aside>
      </div>
    </PublicFrame>
  )
}
