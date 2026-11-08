import { useEffect, useState, type FormEvent } from 'react'
import { BASE } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { PublicFrame } from './RequestTransport'

interface Contact { company: string; officer: string; email: string; reply_days: number; years: number; tracking_days: number; request_days: number }
const KINDS = ['access', 'correction', 'erasure', 'consent', 'complaint'] as const
const field = 'h-11 w-full rounded-lg border border-line bg-surface px-3.5 text-sm outline-none focus:border-ink'

/** The privacy notice (what is kept, why, for how long, who sees it, the person's rights) and the way to use those rights. Public, no sign-in. */
export default function Privacy() {
  const { t } = useI18n()
  const [c, setC] = useState<Contact | null>(null)
  const [f, setF] = useState({ kind: 'access' as (typeof KINDS)[number], phone: '', name: '', message: '', website: '' })
  const [state, setState] = useState<{ ref: string } | 'busy' | 'fail' | null>(null)
  useEffect(() => { fetch(`${BASE}/public/privacy/contact`).then((r) => r.json()).then(setC).catch(() => undefined) }, [])

  async function send(e: FormEvent) {
    e.preventDefault()
    setState('busy')
    try {
      const r = await fetch(`${BASE}/public/privacy`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...f, name: f.name || null, message: f.message || null }) })
      if (!r.ok) throw new Error('refused')
      setState({ ref: ((await r.json()) as { reference: string }).reference })
    } catch { setState('fail') }
  }
  const days = c?.reply_days ?? 30
  const section = 'space-y-2'
  const h = 'text-lg font-semibold'
  return (
    <PublicFrame>
      <article className="space-y-8">
        <header className="space-y-3">
          <h1 className="text-3xl font-semibold tracking-tight">{t('priv.title')}</h1>
          <p className="text-muted">{t('priv.intro', { company: c?.company ?? 'CargoOne' })}</p>
        </header>
        <section className={section}>
          <h2 className={h}>{t('priv.h.what')}</h2>
          <ul className="list-disc space-y-2 pl-5 text-sm text-muted marker:text-line">
            {(['receiver', 'pod', 'driver', 'request'] as const).map((k) => <li key={k}>{t(`priv.w.${k}`)}</li>)}
          </ul>
        </section>
        <section className={section}><h2 className={h}>{t('priv.h.who')}</h2><p className="text-sm text-muted">{t('priv.who')}</p></section>
        <section className={section}>
          <h2 className={h}>{t('priv.h.long')}</h2>
          <p className="text-sm text-muted">{t('priv.long', { years: String(c?.years ?? 8), days: String(c?.tracking_days ?? 30), req: String(c?.request_days ?? 180) })}</p>
        </section>
        <section className={section}><h2 className={h}>{t('priv.h.rights')}</h2><p className="text-sm text-muted">{t('priv.rights')}</p></section>
        <section aria-label={t('priv.h.ask')} className="space-y-4 rounded-2xl border border-line p-6">
          <h2 className={h}>{t('priv.h.ask')}</h2>
          <p className="text-sm text-muted">{t('priv.ask', { days: String(days) })}</p>
          {state !== null && typeof state === 'object'
            ? <p role="status" className="rounded-lg bg-ok-soft px-4 py-3 text-sm font-medium text-ok">{t('priv.sent', { ref: state.ref, days: String(days) })}</p>
            : (
              <form onSubmit={(e) => void send(e)} className="space-y-3">
                <label className="block space-y-1 text-sm"><span className="font-medium">{t('priv.kind')}</span>
                  <select className={field} value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value as typeof f.kind })}>{KINDS.map((k) => <option key={k} value={k}>{t(`priv.k.${k}`)}</option>)}</select></label>
                <label className="block space-y-1 text-sm"><span className="font-medium">{t('priv.phone')}</span>
                  <input className={field} required inputMode="numeric" autoComplete="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></label>
                <label className="block space-y-1 text-sm"><span className="font-medium">{t('priv.name')}</span>
                  <input className={field} maxLength={120} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
                <label className="block space-y-1 text-sm"><span className="font-medium">{t('priv.message')}</span>
                  <textarea className={`${field} h-24 py-2.5`} maxLength={500} value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} /></label>
                <input tabIndex={-1} autoComplete="off" aria-hidden className="sr-only" value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} />
                {state === 'fail' && <p role="alert" className="text-sm text-bad">{t('priv.fail')}</p>}
                <button disabled={state === 'busy'} className="rounded-lg bg-ink px-5 py-2.5 text-sm font-medium text-surface disabled:opacity-60">{t('priv.send')}</button>
              </form>
            )}
          {c && (c.officer || c.email) && <p className="text-sm text-muted">{t('priv.contact', { name: c.officer, email: c.email })}</p>}
        </section>
      </article>
    </PublicFrame>
  )
}
