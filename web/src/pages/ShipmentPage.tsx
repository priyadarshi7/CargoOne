import { Check, CircleDot, Clock, LinkIcon, LoaderCircle, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import ClientFrame from '../components/ClientFrame'
import { LiveMap } from '../components/LiveMap'
import { BASE } from '../lib/api'
import { LANGUAGES, useI18n, type Key, type Lang } from '../lib/i18n'

interface Step { key: string; done: boolean; at: string | null }
interface Row { kind: string; at: string; reason: string | null; minutes: number | null; eta: string | null; note?: string | null }
interface Page {
  audience: 'client' | 'receiver'; company: string; language: Lang; trip_code: string; lr_no: string; origin: string; destination: string; vehicle: string
  material: string | null; weight_tonnes: number | null; packages: number | null; planned_start: string | null; planned_end: string | null
  state: 'planned' | 'in_transit' | 'delivered' | 'cancelled'; cancelled: boolean; delivered_at: string | null; delivery_issue: boolean
  steps: Step[]; timeline: Row[]; live: { lat: number | null; lng: number | null; seen_at: string | null; eta: string | null } | null
  delivery_code?: string
  client_name?: string; freight_amount?: number; consignee_name?: string | null; eway_bill_no?: string; pod_available?: boolean
  invoice?: { invoice_no: string; total: number; sent_at: string; paid_at: string | null } | null
}
type State = { kind: 'loading' } | { kind: 'ok'; p: Page } | { kind: 'unknown' } | { kind: 'error' }

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })

/** One shipment, one page: where it is, what has happened, and what this person needs (the client: price, proof, invoice; the receiver: the delivery code). */
export default function ShipmentPage() {
  const { token = '' } = useParams()
  const { t, date, lang, setLang } = useI18n()
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [pod, setPod] = useState<string | null>(null)
  const [first, setFirst] = useState(true)

  useEffect(() => {
    let alive = true
    const load = () => fetch(`${BASE}/public/shipments/${encodeURIComponent(token)}`)
      .then(async (r) => {
        if (!alive) return
        if (r.ok) return setState({ kind: 'ok', p: (await r.json()) as Page })
        setState({ kind: r.status === 404 ? 'unknown' : 'error' })
      })
      .catch(() => alive && setState((s) => (s.kind === 'ok' ? s : { kind: 'error' })))
    void load()
    const id = setInterval(() => void load(), 30_000)
    return () => { alive = false; clearInterval(id) }
  }, [token])

  const p = state.kind === 'ok' ? state.p : null
  useEffect(() => { // the page opens in the client's language, unless this visitor has already picked one
    if (!p || !first) return
    setFirst(false)
    try { if (!localStorage.getItem('cargoone.lang')) setLang(p.language) } catch { setLang(p.language) }
  }, [p, first, setLang])

  useEffect(() => {
    if (!p?.pod_available) return
    let url: string | null = null
    fetch(`${BASE}/public/shipments/${encodeURIComponent(token)}/pod`).then((r) => (r.ok ? r.blob() : null)).then((b) => { if (b) { url = URL.createObjectURL(b); setPod(url) } }).catch(() => undefined)
    return () => { if (url) URL.revokeObjectURL(url) }
  }, [p?.pod_available, token])

  if (state.kind === 'loading') return <Msg icon={<LoaderCircle size={40} className="animate-spin text-accent" aria-label="Loading" />} text="" />
  if (state.kind === 'unknown') return <Msg icon={<LinkIcon size={40} className="text-bad" />} text={t('shp.unknown')} />
  if (state.kind === 'error') return <Msg icon={<Clock size={40} className="text-accent" />} text={t('shp.error')} />
  const x = state.p

  const eta = x.live?.eta ? date(x.live.eta, true) : null
  const headline = x.cancelled ? t('shp.h.cancelled')
    : x.state === 'delivered' ? t('shp.h.delivered', { when: x.delivered_at ? date(x.delivered_at, true) : '' })
    : x.state === 'in_transit' ? (eta ? t('shp.h.eta', { eta }) : t('shp.h.road'))
    : x.steps.find((s) => s.key === 'loaded')?.done ? t('shp.h.loaded')
    : t('shp.h.planned', { when: x.planned_start ? date(x.planned_start, true) : '-' })
  const tone = x.cancelled ? 'bg-bad-soft text-bad' : x.state === 'delivered' ? 'bg-ok-soft text-ok' : 'bg-accent-soft text-accent'
  const goods = [x.material, x.weight_tonnes ? `${x.weight_tonnes} t` : null, x.packages ? `${x.packages} pkg` : null].filter(Boolean).join(' · ')
  const mins = x.live?.seen_at ? Math.max(0, Math.round((Date.now() - new Date(x.live.seen_at).getTime()) / 60_000)) : null
  const facts: [string, string | null][] = [[t('shp.goods'), goods || null], [t('shp.truck'), x.vehicle], [t('shp.lr'), x.lr_no], [t('shp.consignee'), x.consignee_name ?? null], [t('shp.freight'), x.freight_amount != null ? inr.format(x.freight_amount) : null]]
  const detail = (r: Row) => [r.reason ? t(`drv.r.${r.reason}` as Key) : null, r.minutes ? t('drv.pMin', { n: r.minutes }) : null, r.eta ? date(r.eta, true) : null, r.note].filter(Boolean).join(' · ')

  return (
    <ClientFrame className="space-y-6">
      <header className="space-y-1">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-muted">{x.company}</p>
          <select aria-label={t('shp.lang')} value={lang} onChange={(e) => setLang(e.target.value as Lang)} className="h-9 rounded-lg border border-line bg-surface px-2 text-sm">
            {LANGUAGES.map(([l, name]) => <option key={l} value={l}>{name}</option>)}
          </select>
        </div>
        <h1 className="text-3xl font-semibold tracking-tight">{x.audience === 'client' ? t('shp.client') : t('shp.receiver')}</h1>
        <p className="text-sm text-muted">{x.trip_code}</p>
        <p className="flex flex-wrap items-center gap-x-2 pt-1 text-lg font-medium"><span>{x.origin}</span><span className="text-muted">→</span><span>{x.destination}</span></p>
      </header>

      <p role="status" className={`rounded-xl px-4 py-4 text-lg font-semibold ${tone}`}>{headline}</p>

      {x.delivery_code && (
        <section aria-label={t('shp.codeTitle')} className="space-y-2 rounded-2xl border border-line p-5 text-center">
          <h2 className="text-sm font-medium uppercase tracking-wider text-muted">{t('shp.codeTitle')}</h2>
          <p className="text-6xl font-semibold tabular-nums tracking-[0.3em]" aria-label={x.delivery_code.split('').join(' ')}>{x.delivery_code}</p>
          <p className="text-sm text-muted">{t('shp.codeHelp')}</p>
        </section>
      )}

      <ol aria-label="Progress" className={`grid items-start gap-x-1 gap-y-4 ${x.steps.length > 5 ? 'grid-cols-4' : 'grid-cols-5'}`}>
        {x.steps.map((s) => (
          <li key={s.key} className="flex flex-col items-center gap-1.5 text-center text-xs">
            <span className={`grid h-7 w-7 place-items-center rounded-full ${s.done ? 'bg-ok text-on-solid' : 'border border-line text-muted'}`}>{s.done ? <Check size={15} aria-hidden /> : <CircleDot size={13} aria-hidden />}</span>
            <span className={s.done ? 'font-medium' : 'text-muted'}>{t(`ev.${s.key}` as Key)}</span>
          </li>
        ))}
      </ol>

      {x.state === 'in_transit' && (x.live?.lat != null && x.live.lng != null ? (
        <section className="space-y-2">
          <div className="h-[22rem]"><LiveMap label="Map" points={[{ id: 'load', lat: x.live.lat, lng: x.live.lng, label: x.vehicle, tone: 'ok' }]} /></div>
          {mins !== null && <p className="text-sm text-muted">{t('shp.live', { mins })}</p>}
        </section>
      ) : <p className="rounded-xl bg-wash px-4 py-4 text-muted">{t('shp.noPos')}</p>)}

      {x.delivery_issue && <p className="flex items-start gap-2 rounded-xl bg-warn-soft px-4 py-3 text-warn"><TriangleAlert size={18} className="mt-0.5 shrink-0" aria-hidden /> {t('shp.issue')}</p>}

      <dl className="divide-y divide-line rounded-xl border border-line text-sm">
        {facts.filter(([, v]) => v).map(([k, v]) => <div key={k} className="flex justify-between gap-4 px-4 py-2.5"><dt className="text-muted">{k}</dt><dd className="text-right font-medium">{v}</dd></div>)}
      </dl>

      {x.invoice && (
        <p className="rounded-xl border border-line px-4 py-3 text-sm">
          {t('shp.invoiceSent', { no: x.invoice.invoice_no, amount: inr.format(x.invoice.total), when: date(x.invoice.sent_at) })}
          {x.invoice.paid_at && <span className="mt-1 block font-medium text-ok">{t('shp.invoicePaid', { when: date(x.invoice.paid_at) })}</span>}
        </p>
      )}
      {pod && <section className="space-y-2"><h2 className="font-semibold">{t('shp.pod')}</h2><img src={pod} alt={t('shp.pod')} className="w-full rounded-xl border border-line" /></section>}

      {x.timeline.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-semibold">{t('shp.timeline')}</h2>
          <ol className="space-y-3 border-l border-line pl-4 text-sm">
            {[...x.timeline].reverse().map((r, i) => (
              <li key={i} className="relative">
                <span aria-hidden className="absolute -left-[1.3rem] top-1.5 h-2 w-2 rounded-full bg-ink" />
                <p className="font-medium">{t(`ev.${r.kind}` as Key)} <span className="font-normal text-muted">· {date(r.at, true)}</span></p>
                {detail(r) && <p className="text-muted">{detail(r)}</p>}
              </li>
            ))}
          </ol>
        </section>
      )}
      <p className="text-xs text-muted">{t('shp.footer')}</p>
    </ClientFrame>
  )
}

function Msg({ icon, text }: { icon: React.ReactNode; text: string }) {
  return <main className="grid min-h-screen place-items-center px-6"><div className="flex max-w-sm flex-col items-center gap-4 text-center">{icon}<p>{text}</p></div></main>
}
