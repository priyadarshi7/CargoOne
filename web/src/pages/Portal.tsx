import { Truck } from 'lucide-react'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { ThemeToggle } from '../components/ThemeToggle'
import PhoneInput from '../components/PhoneInput'
import PlaceInput from '../components/PlaceInput'
import { api, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { LANGUAGES, useI18n, type Key, type Lang } from '../lib/i18n'
import Account from './Account'

interface Shipment { trip_code: string; origin: string; destination: string; stage: string; planned_start: string | null; delivered_at: string | null; freight_amount: number; token: string }
interface Req { reference: string; status: 'new' | 'accepted' | 'booked' | 'declined'; origin: string; destination: string; material: string; pickup_date: string; quote_amount: number | null; needs_reply: boolean; token: string }

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const TONE: Record<string, string> = { paid: 'bg-ok-soft text-ok', delivered: 'bg-ok-soft text-ok', verified: 'bg-ok-soft text-ok', invoiced: 'bg-accent-soft text-accent', started: 'bg-accent-soft text-accent', cancelled: 'bg-wash text-muted', booked: 'bg-wash text-ink', loaded: 'bg-wash text-ink' }

/** The frame of a client's own pages: their company, three places to go, language, theme, sign out. */
export function PortalShell({ children }: { children: ReactNode }) {
  const { t, lang, setLang } = useI18n()
  const { user, logout } = useAuth()
  const link = ({ isActive }: { isActive: boolean }) => `rounded-lg px-3 py-1.5 text-sm ${isActive ? 'bg-accent-soft font-medium text-accent' : 'text-muted hover:text-ink'}`
  return (
    <div className="min-h-full">
      <header className="border-b border-line">
        <div className="mx-auto flex min-h-14 max-w-4xl flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2 sm:px-6">
          <Link to="/portal" className="flex items-center gap-2.5 text-base font-semibold tracking-tight"><span className="grid h-7 w-7 place-items-center rounded-lg bg-ink text-surface"><Truck size={15} aria-hidden /></span> CargoOne</Link>
          <nav className="flex gap-1">
            <NavLink to="/portal" end className={link}>{t('portal.ship')}</NavLink>
            <NavLink to="/portal/new" className={link}>{t('portal.new')}</NavLink>
            <NavLink to="/portal/account" className={link}>{t('portal.account')}</NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden text-sm text-muted sm:inline">{user?.name}</span>
            <select aria-label={t('shp.lang')} value={lang} onChange={(e) => setLang(e.target.value as Lang)} className="h-9 rounded-lg border border-line bg-surface px-2 text-sm">{LANGUAGES.map(([l, n]) => <option key={l} value={l}>{n}</option>)}</select>
            <ThemeToggle />
            <button onClick={logout} className="h-9 rounded-lg px-2.5 text-sm text-muted hover:bg-wash hover:text-ink">{t('portal.signOut')}</button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-6">{children}</main>
    </div>
  )
}

export function PortalAccount() { return <PortalShell><Account /></PortalShell> }

/** A client's home: every shipment of theirs and where it stands, and the requests that wait for an answer. Each row opens the shipment page. */
export default function Portal() {
  const { t, date } = useI18n()
  const [ships, setShips] = useState<Shipment[] | null>(null)
  const [reqs, setReqs] = useState<Req[] | null>(null)
  const [me, setMe] = useState<{ company: string } | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    Promise.all([api<Shipment[]>('/portal/shipments'), api<Req[]>('/portal/requests'), api<{ company: string }>('/portal/me')]).then(([s, r, m]) => { setShips(s); setReqs(r); setMe(m) }).catch(() => setError(true))
  }, [])
  const open = (reqs ?? []).filter((r) => r.status === 'new' || r.status === 'accepted')

  return (
    <PortalShell>
      <div><h1 className="text-3xl font-semibold tracking-tight">{t('portal.title')}</h1>{me && <p className="text-sm text-muted">{me.company}</p>}</div>
      {error ? <p role="alert" className="text-bad">{t('shp.error')}</p> : !ships || !reqs ? <p className="text-muted">…</p> : (
        <>
          {open.length > 0 && (
            <section aria-label={t('portal.req')} className="space-y-2">
              <h2 className="font-semibold">{t('portal.req')}</h2>
              <ul className="divide-y divide-line rounded-xl border border-line">
                {open.map((r) => (
                  <li key={r.reference}>
                    <Link to={`/request/${r.token}`} className="flex flex-wrap items-center gap-x-5 gap-y-1 px-4 py-3 hover:bg-wash">
                      <span className="min-w-24 font-medium tabular-nums">{r.reference}</span>
                      <span className="text-muted">{r.origin} → {r.destination}</span>
                      {r.needs_reply && <span className="rounded-full bg-warn-soft px-2.5 py-0.5 text-xs font-medium text-warn">{t('portal.needsReply')}</span>}
                      <span className="ml-auto rounded-full bg-wash px-2.5 py-0.5 text-xs">{t(`req.status.${r.status}` as Key)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <section aria-label={t('portal.ship')} className="space-y-2">
            <h2 className="font-semibold">{t('portal.ship')}</h2>
            {ships.length === 0 ? <p className="rounded-xl border border-line px-4 py-8 text-center text-muted">{t('portal.noShip')}</p> : (
              <ul className="divide-y divide-line rounded-xl border border-line">
                {ships.map((s) => (
                  <li key={s.trip_code}>
                    <Link to={`/s/${s.token}`} aria-label={`${t('portal.open')} ${s.trip_code}`} className="flex flex-wrap items-center gap-x-5 gap-y-1 px-4 py-3 hover:bg-wash">
                      <span className="min-w-24 font-medium tabular-nums">{s.trip_code}</span>
                      <span className="text-muted">{s.origin} → {s.destination}</span>
                      <span className="text-sm text-muted">{s.delivered_at ? date(s.delivered_at) : s.planned_start ? date(s.planned_start) : ''}</span>
                      <span className="ml-auto flex items-center gap-3"><span className="text-sm tabular-nums">{inr.format(s.freight_amount)}</span><span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE[s.stage] ?? 'bg-wash'}`}>{t(`ev.${s.stage}` as Key)}</span></span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </PortalShell>
  )
}

/** Ask for the next truck: the company is already known, so only the route and the goods are asked. */
export function PortalNew() {
  const { t } = useI18n()
  const nav = useNavigate()
  const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
  const [hasPhone, setHasPhone] = useState(true)
  useEffect(() => { api<{ has_phone: boolean }>('/portal/me').then((m) => setHasPhone(m.has_phone)).catch(() => undefined) }, [])
  const [f, setF] = useState({ phone: '', origin: '', destination: '', origin_lat: null as number | null, origin_lng: null as number | null, destination_lat: null as number | null, destination_lng: null as number | null, material: '', weight_tonnes: '', truck_type: '', pickup_date: '', notes: '' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const field = 'h-11 w-full rounded-lg border border-line bg-surface px-3.5 text-sm outline-none focus:border-ink'
  const label = (text: string, input: ReactNode) => <label className="block space-y-1.5 text-sm"><span className="font-medium">{text}</span>{input}</label>
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })

  async function send(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      const made = await api<{ reference: string; token: string }>('/portal/requests', { method: 'POST', body: JSON.stringify({ ...f, weight_tonnes: f.weight_tonnes || null, truck_type: f.truck_type || null, notes: f.notes || null, phone: f.phone || null }) })
      nav(`/request/${made.token}`)
    } catch (err) { setError(err instanceof ApiError ? err.message : t('shp.error')) } finally { setBusy(false) }
  }

  return (
    <PortalShell>
      <div><h1 className="text-3xl font-semibold tracking-tight">{t('portal.newTitle')}</h1><p className="text-sm text-muted">{t('portal.newHelp')}</p></div>
      <form onSubmit={(e) => void send(e)} className="max-w-xl space-y-4">
        <PlaceInput label={t('req.origin')} required value={f.origin} lat={f.origin_lat} lng={f.origin_lng} onChange={(text, pos) => setF({ ...f, origin: text, origin_lat: pos?.lat ?? null, origin_lng: pos?.lng ?? null })} />
        <PlaceInput label={t('req.destination')} required value={f.destination} lat={f.destination_lat} lng={f.destination_lng} onChange={(text, pos) => setF({ ...f, destination: text, destination_lat: pos?.lat ?? null, destination_lng: pos?.lng ?? null })} />
        <div className="grid gap-4 sm:grid-cols-2">
          {label(t('req.material'), <input className={field} required minLength={2} maxLength={160} value={f.material} onChange={set('material')} />)}
          {label(t('req.weight'), <input className={field} inputMode="decimal" value={f.weight_tonnes} onChange={set('weight_tonnes')} />)}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {label(t('req.truck'), <input className={field} maxLength={60} value={f.truck_type} onChange={set('truck_type')} />)}
          {label(t('req.pickup'), <input type="date" className={field} required min={today} value={f.pickup_date} onChange={set('pickup_date')} />)}
        </div>
        {!hasPhone && <PhoneInput label={t('req.phone')} required value={f.phone} onChange={(v) => setF({ ...f, phone: v })} />}
        {label(t('req.notes'), <input className={field} maxLength={500} value={f.notes} onChange={set('notes')} />)}
        {error && <p role="alert" className="rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn">{error}</p>}
        <button disabled={busy} className="rounded-lg bg-ink px-5 py-2.5 text-sm font-medium text-surface disabled:opacity-60">{t('portal.send')}</button>
      </form>
    </PortalShell>
  )
}
