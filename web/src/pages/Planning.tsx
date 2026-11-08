import { Plus, TriangleAlert, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, ApiError, download, type TripState } from '../lib/api'
import PhoneInput from '../components/PhoneInput'
import PlaceInput from '../components/PlaceInput'
import { DocSlots, TRIP_DOCS } from './setup/Docs'
import { useAuth } from '../lib/auth'
import { LANGUAGES, useI18n } from '../lib/i18n'

interface BoardTrip { id: string; trip_code: string; lr_no: string; client: string; vehicle_id: string; driver_id: string | null; driver: string | null; origin: string; destination: string; state: TripState; planned_start: string | null; planned_end: string | null; started_at: string | null }
interface Vehicle { id: string; reg_no: string; is_hired: boolean; availability?: string; capacity_tonnes?: number | null }
interface Prefill { id: string; reference: string; client_id: string; origin: string; destination: string; origin_lat?: number | null; origin_lng?: number | null; destination_lat?: number | null; destination_lng?: number | null; material: string; weight_tonnes: number | null; pickup_date: string; quote_amount?: number | null }
interface Board { now: string; vehicles: Vehicle[]; trips: BoardTrip[] }
interface Refs { clients: { id: string; name: string }[]; vehicles: Vehicle[]; drivers: { id: string; name: string; assigned_vehicle_id?: string | null }[]; branches: { id: string; name: string }[]; default_origin: string }

const DAY = 86_400_000
const DAYS = 15 // yesterday + two weeks
const LANE = 44 // px per lane: a truck with overlapping trips gets one lane for each
const BAR: Record<TripState, string> = {
  planned: 'border border-dashed border-accent bg-accent-soft text-accent',
  in_transit: 'bg-ink text-surface',
  delivered: 'bg-ok-soft text-ok',
  cancelled: 'bg-wash text-muted',
}
const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
const toLocalInput = (iso: string | null) => (iso ? new Date(new Date(iso).getTime() - new Date(iso).getTimezoneOffset() * 60_000).toISOString().slice(0, 16) : '')
const fromLocalInput = (v: string) => (v ? new Date(v).toISOString() : null)
const nowInput = () => toLocalInput(new Date(Date.now() - 10 * 60_000).toISOString()) // the earliest start the server accepts is about now
const prefillStart = (day: string) => { const eight = `${day}T08:00`; const now = nowInput(); return eight < now ? now : eight } // a pickup today after 8 am starts "now"

/** Trip planning board: a 15-day timeline per vehicle. Dashed = planned, solid = on the road, green = delivered. */
export default function Planning() {
  const { user } = useAuth()
  const { t, lang } = useI18n()
  const canPlan = user?.role === 'ops' || user?.role === 'admin'
  const [board, setBoard] = useState<Board | null>(null)
  const [refs, setRefs] = useState<Refs | null>(null)
  const [error, setError] = useState(false)
  const [dialog, setDialog] = useState<{ trip: BoardTrip | null; prefill?: Prefill } | null>(null)
  const [params, setParams] = useSearchParams()
  const requestId = params.get('request')
  useEffect(() => {
    if (!requestId || !canPlan) return
    api<(Prefill & { status: string })[]>('/requests?state=open').then((all) => {
      const r = all.find((x) => x.id === requestId && x.status === 'accepted')
      if (r) setDialog({ trip: null, prefill: r })
      setParams({}, { replace: true })
    }).catch(() => undefined)
  }, [requestId, canPlan, setParams])

  const load = useCallback(async () => {
    try {
      const [b, r] = await Promise.all([api<Board>('/planning/board'), api<Refs>('/planning/refs')])
      setBoard(b)
      setRefs(r)
    } catch { setError(true) }
  }, [])
  useEffect(() => { void load() }, [load])

  const range = useMemo(() => {
    const from = startOfDay(new Date(board?.now ?? Date.now())) - DAY
    return { from, to: from + DAYS * DAY }
  }, [board?.now])

  if (error) return <p className="text-bad">{t('plan.error')}</p>
  if (!board || !refs) return <p className="text-muted">{t('common.loading')}</p>

  const slot = (tr: BoardTrip) => {
    const s = tr.started_at ?? tr.planned_start
    if (!s) return null
    const a = new Date(s).getTime()
    const b = tr.planned_end ? new Date(tr.planned_end).getTime() : a + DAY
    return { a, b: Math.max(b, a + DAY / 6) }
  }
  const scheduled = board.trips.filter((x) => slot(x))
  const unscheduled = board.trips.filter((x) => !slot(x) && (x.state === 'planned' || x.state === 'in_transit'))
  const pct = (ms: number) => Math.min(100, Math.max(0, ((ms - range.from) / (range.to - range.from)) * 100))
  const dayLabel = (i: number) => new Date(range.from + i * DAY).toLocaleDateString(lang === 'en' ? 'en-IN' : `${lang}-IN`, { day: 'numeric', weekday: 'short' })
  const todayIdx = Math.floor((startOfDay(new Date(board.now)) - range.from) / DAY)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{t('plan.title')}</h1>
          <p className="text-sm text-muted">{t('plan.sub')}</p>
        </div>
        {canPlan && (
          <button onClick={() => setDialog({ trip: null })} className="inline-flex items-center gap-1.5 rounded-lg bg-ink px-4 py-2 text-sm font-medium text-surface">
            <Plus size={16} aria-hidden /> {t('plan.new')}
          </button>
        )}
      </div>

      <ul className="flex flex-wrap gap-4 text-xs text-muted" aria-label={t('plan.legend')}>
        {(['planned', 'in_transit', 'delivered'] as const).map((s) => (
          <li key={s} className="inline-flex items-center gap-1.5"><span className={`inline-block h-3 w-6 rounded ${BAR[s]}`} />{t(`state.${s}`)}</li>
        ))}
      </ul>

      {board.vehicles.length === 0 ? <p className="text-muted">{t('plan.noVehicles')}</p> : (
        <div className="overflow-x-auto rounded-xl border border-line">
          <div className="min-w-[860px]">
            <div className="grid grid-cols-[10.5rem_1fr] border-b border-line bg-wash text-xs text-muted">
              <div className="px-3 py-2">{t('plan.vehicle')}</div>
              <div className="grid" style={{ gridTemplateColumns: `repeat(${DAYS}, 1fr)` }}>
                {Array.from({ length: DAYS }, (_, i) => (
                  <div key={i} className={`border-l border-line px-1 py-2 text-center ${i === todayIdx ? 'font-semibold text-accent' : ''}`}>{dayLabel(i)}</div>
                ))}
              </div>
            </div>
            {board.vehicles.map((v) => {
              // trips of one truck that overlap in time go in separate lanes, so none is ever drawn on top of another
              const mine = scheduled.filter((x) => x.vehicle_id === v.id && pct(slot(x)!.b) > pct(slot(x)!.a)).sort((p, q) => slot(p)!.a - slot(q)!.a)
              const laneEnds: number[] = []
              const placed = mine.map((x) => {
                const s = slot(x)!
                const visualEnd = Math.max(s.b, s.a + DAY * 0.9) // a bar is at least about a day wide on screen
                let lane = laneEnds.findIndex((e) => e <= s.a)
                if (lane < 0) lane = laneEnds.length
                laneEnds[lane] = visualEnd
                return { x, s, lane }
              })
              const lanes = Math.max(1, laneEnds.length)
              return (
                <div key={v.id} className="grid grid-cols-[10.5rem_1fr] border-b border-line last:border-0">
                  <div className="px-3 py-3 text-sm font-medium">{v.reg_no}{v.is_hired && <span className="ml-1.5 text-xs font-normal text-muted">{t('plan.hiredTag')}</span>}{lanes > 1 && <span className="ml-1.5 text-xs font-normal text-muted">{t('plan.overlap', { n: mine.length })}</span>}</div>
                  <div className="relative" style={{ height: lanes * LANE + 8 }}>
                    <div className="absolute inset-0 grid" style={{ gridTemplateColumns: `repeat(${DAYS}, 1fr)` }} aria-hidden>
                      {Array.from({ length: DAYS }, (_, i) => <div key={i} className={`border-l border-line ${i === todayIdx ? 'bg-accent-soft/50' : ''}`} />)}
                    </div>
                    {placed.map(({ x, s, lane }) => {
                      const left = pct(s.a), right = pct(s.b)
                      return (
                        <button key={x.id} onClick={() => setDialog({ trip: x })} title={`${x.trip_code} · ${x.origin} → ${x.destination}${x.driver ? ` · ${x.driver}` : ''}`}
                          aria-label={t('plan.opens', { code: x.trip_code })}
                          className={`absolute h-9 min-w-[3.25rem] overflow-hidden rounded-md px-2 text-left text-xs font-medium leading-tight ${BAR[x.state]}`}
                          style={{ left: `${left}%`, width: `${Math.max(right - left, 0.5)}%`, top: lane * LANE + 6 }}>
                          <span className="block truncate">{x.destination}</span>
                          <span className="block truncate opacity-80">{x.driver ?? t('plan.noDriver')}</span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {unscheduled.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-semibold">{t('plan.unscheduled')}</h2>
          <ul className="divide-y divide-line rounded-xl border border-line text-sm">
            {unscheduled.map((x) => {
              const veh = board.vehicles.find((v) => v.id === x.vehicle_id)
              return (
                <li key={x.id}>
                  <button onClick={() => setDialog({ trip: x })} className="flex w-full flex-wrap items-center gap-x-6 gap-y-1 px-4 py-3 text-left hover:bg-wash" aria-label={t('plan.opens', { code: x.trip_code })}>
                    <span className="min-w-28 font-medium">{x.trip_code}</span>
                    <span className="text-muted">{x.origin} → {x.destination}</span>
                    <span className="text-muted">{veh?.reg_no}{x.driver ? ` · ${x.driver}` : ''}</span>
                    <span className={`ml-auto rounded-full px-2.5 py-0.5 text-xs ${BAR[x.state]}`}>{t(`state.${x.state}`)}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </section>
      )}

      {dialog && <TripDialog trip={dialog.trip} prefill={dialog.prefill} refs={refs} canPlan={canPlan} onClose={() => setDialog(null)} onSaved={() => { setDialog(null); void load() }} />}
    </div>
  )
}

function TripDialog({ trip, prefill, refs, canPlan, onClose, onSaved }: { trip: BoardTrip | null; prefill?: Prefill; refs: Refs; canPlan: boolean; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n()
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { ref.current?.showModal() }, [])
  const editing = trip !== null
  const locked = editing && (trip.state !== 'planned' || !canPlan)
  const [f, setF] = useState({
    client_id: prefill?.client_id ?? refs.clients[0]?.id ?? '', vehicle_id: trip?.vehicle_id ?? refs.vehicles[0]?.id ?? '', driver_id: trip?.driver_id ?? '',
    origin: prefill?.origin ?? refs.default_origin, destination: prefill?.destination ?? trip?.destination ?? '', origin_lat: (prefill?.origin_lat ?? null) as number | null, origin_lng: (prefill?.origin_lng ?? null) as number | null, destination_lat: (prefill?.destination_lat ?? null) as number | null, destination_lng: (prefill?.destination_lng ?? null) as number | null, freight_amount: prefill?.quote_amount != null ? String(prefill.quote_amount) : '', eway_bill_no: '', material: prefill?.material ?? '', weight_tonnes: prefill?.weight_tonnes?.toString() ?? '', packages: '', consignee_name: '', consignee_phone: '', consignee_email: '', consignee_language: 'en',
    start: prefill ? prefillStart(prefill.pickup_date) : toLocalInput(trip?.planned_start ?? null), end: toLocalInput(trip?.planned_end ?? null), eway_until: '', reason: '',
  })
  const [error, setError] = useState<string | null>(null)
  const [clash, setClash] = useState(false)
  const [busy, setBusy] = useState(false)
  const [confirmCancel, setConfirmCancel] = useState(false)
  const [cancelReason, setCancelReason] = useState('')
  const [created, setCreated] = useState<{ trip_code: string; lr_no: string; id: string } | null>(null)
  const set = (k: keyof typeof f, v: string) => { setF({ ...f, [k]: v }); setClash(false) }
  const pickDriver = (id: string) => {
    const own = refs.drivers.find((d) => d.id === id)?.assigned_vehicle_id // a driver normally drives one truck: suggest it
    setF({ ...f, driver_id: id, vehicle_id: own && refs.vehicles.some((v) => v.id === own && v.availability !== 'maintenance' && v.availability !== 'breakdown') ? own : f.vehicle_id })
    setClash(false)
  }
  const usable = refs.vehicles.filter((v) => v.id === trip?.vehicle_id || !v.availability || v.availability === 'available')

  async function save(e: FormEvent, force = false) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const times = { planned_start: fromLocalInput(f.start), planned_end: fromLocalInput(f.end) }
    try {
      if (editing) {
        await api(`/planning/trips/${trip.id}`, { method: 'PATCH', body: JSON.stringify({ vehicle_id: f.vehicle_id, driver_id: f.driver_id || null, ...times, reason: f.reason || null, force }) })
      } else {
        const made = await api<{ id: string; trip_code: string; lr_no: string }>('/planning/trips', { method: 'POST', body: JSON.stringify({
          client_id: f.client_id, vehicle_id: f.vehicle_id, driver_id: f.driver_id || null, origin: f.origin || null, destination: f.destination, origin_lat: f.origin_lat, origin_lng: f.origin_lng, destination_lat: f.destination_lat, destination_lng: f.destination_lng,
          freight_amount: f.freight_amount, eway_bill_no: f.eway_bill_no, material: f.material || null, weight_tonnes: f.weight_tonnes || null,
          packages: f.packages || null, request_id: prefill?.id ?? null, consignee_name: f.consignee_name || null, consignee_phone: f.consignee_phone || null, consignee_email: f.consignee_email || null, consignee_language: f.consignee_language, ...times, eway_valid_until: fromLocalInput(f.eway_until), force }) })
        setCreated(made)
        return
      }
      onSaved()
    } catch (err) {
      setClash(err instanceof ApiError && err.status === 409 && typeof err.detail === 'object')
      setError(err instanceof ApiError ? err.message : t('plan.failed'))
    } finally {
      setBusy(false)
    }
  }

  async function cancel() {
    setBusy(true)
    try { await api(`/planning/trips/${trip!.id}/cancel`, { method: 'POST', body: JSON.stringify({ reason: cancelReason }) }); onSaved() }
    catch (err) { setError(err instanceof ApiError ? err.message : t('plan.failed')); setConfirmCancel(false); setBusy(false) }
  }

  const field = 'h-11 w-full rounded-lg border border-line bg-surface px-3.5 text-sm outline-none focus:border-ink disabled:opacity-60'
  const label = (text: string, input: React.ReactNode) => <label className="block space-y-1.5 text-sm"><span className="font-medium">{text}</span>{input}</label>
  const sec = (title: string) => <h3 className="border-t border-line pt-4 text-xs font-medium uppercase tracking-wider text-muted first:border-0 first:pt-0">{title}</h3>
  return (
    <dialog ref={ref} onClose={created ? onSaved : onClose} aria-label={editing ? trip.trip_code : t('plan.new')} className="m-auto max-h-[92vh] w-[min(40rem,94vw)] overflow-y-auto rounded-2xl border border-line bg-surface p-0 text-ink shadow-xl backdrop:bg-black/30">
      {created ? (
        <div className="space-y-4 p-6">
          <h2 className="text-lg font-semibold">{t('lr.created', { code: created.trip_code })}</h2>
          <p className="text-2xl font-semibold tabular-nums" aria-label={t('lr.no')}>{created.lr_no}</p>
          <p className="text-sm text-muted">{t('lr.createdLr', { lr: created.lr_no })}</p>
          <div className="flex flex-wrap justify-end gap-3">
            <button type="button" onClick={() => void download(`/trips/${created.id}/lr.pdf`, `${created.trip_code}-LR.pdf`).catch(() => setError(t('lr.pdfFail')))} className="rounded-lg border border-line px-4 py-2 text-sm">{t('lr.download')}</button>
            <button type="button" onClick={onSaved} className="rounded-lg bg-ink px-5 py-2 text-sm font-medium text-surface">{t('lr.done')}</button>
          </div>
          {error && <p role="alert" className="text-sm text-bad">{error}</p>}
        </div>
      ) : (
      <form onSubmit={(e) => void save(e)} className="space-y-4 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">{editing ? trip.trip_code : t('plan.new')}</h2>
            {editing && <p className="text-sm text-muted">{trip.client} · {trip.origin} → {trip.destination}</p>}
          </div>
          <button type="button" onClick={() => ref.current?.close()} aria-label={t('common.close')} className="text-muted hover:text-ink"><X size={20} /></button>
        </div>
        {editing && locked && <p className="rounded-lg bg-wash px-3 py-2 text-sm text-muted">{t('plan.readOnly')}</p>}

        {!editing && (
          <>
            {sec(t('plan.sec.route'))}
            {label(t('plan.client'), <select className={field} value={f.client_id} onChange={(e) => set('client_id', e.target.value)}>{refs.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>)}
            <div className="grid gap-4 sm:grid-cols-2">
              <PlaceInput label={t('plan.origin')} value={f.origin} lat={f.origin_lat} lng={f.origin_lng} onChange={(text, pos) => { setF({ ...f, origin: text, origin_lat: pos?.lat ?? null, origin_lng: pos?.lng ?? null }); setClash(false) }} />
              <PlaceInput label={t('plan.destination')} required value={f.destination} lat={f.destination_lat} lng={f.destination_lng} onChange={(text, pos) => { setF({ ...f, destination: text, destination_lat: pos?.lat ?? null, destination_lng: pos?.lng ?? null }); setClash(false) }} />
            </div>
          </>
        )}
        {sec(t('plan.sec.truck'))}
        <div className="grid gap-4 sm:grid-cols-2">
          {label(t('plan.vehicle'), <select className={field} disabled={locked} value={f.vehicle_id} onChange={(e) => set('vehicle_id', e.target.value)}>{usable.map((v) => <option key={v.id} value={v.id}>{v.reg_no}{v.capacity_tonnes ? ` · ${v.capacity_tonnes} t` : ''}{v.is_hired ? ` (${t('plan.hiredTag')})` : ''}</option>)}</select>)}
          {label(t('plan.driver'), <select className={field} disabled={locked} value={f.driver_id} onChange={(e) => pickDriver(e.target.value)}><option value="">{t('plan.noDriver')}</option>{refs.drivers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>)}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {label(t('plan.start'), <input type="datetime-local" className={field} required disabled={locked} min={editing && f.start === toLocalInput(trip?.planned_start ?? null) ? undefined : nowInput()} max={toLocalInput(new Date(Date.now() + 365 * 86_400_000).toISOString())} value={f.start} onChange={(e) => set('start', e.target.value)} />)}
          {label(t('plan.end'), <input type="datetime-local" className={field} disabled={locked} min={f.start || undefined} value={f.end} onChange={(e) => set('end', e.target.value)} />)}
        </div>
        {editing && !locked && (f.vehicle_id !== trip.vehicle_id || (f.driver_id || null) !== trip.driver_id || f.start !== toLocalInput(trip.planned_start) || f.end !== toLocalInput(trip.planned_end)) && (
          label(t('plan.reason'), <input className={field} required maxLength={300} placeholder={t('plan.reasonPh')} value={f.reason} onChange={(e) => set('reason', e.target.value)} />)
        )}
        {!editing && sec(t('plan.sec.freight'))}
        {!editing && (
          <div className="grid gap-4 sm:grid-cols-3">
            {label(t('plan.freight'), <input className={field} required inputMode="decimal" value={f.freight_amount} onChange={(e) => set('freight_amount', e.target.value)} />)}
            {label(t('plan.eway'), <input className={field} required inputMode="numeric" maxLength={12} value={f.eway_bill_no} onChange={(e) => set('eway_bill_no', e.target.value.replace(/\D/g, ''))} />)}
            {label(t('plan.ewayUntil'), <input type="datetime-local" className={field} required min={f.start || nowInput()} value={f.eway_until} onChange={(e) => set('eway_until', e.target.value)} />)}
            <p className="text-xs text-muted sm:col-span-3">{t('lr.auto')}</p>
          </div>
        )}
        {!editing && (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              {label(t('plan.material'), <input className={field} maxLength={160} value={f.material} onChange={(e) => set('material', e.target.value)} />)}
              {label(t('plan.weight'), <input className={field} inputMode="decimal" value={f.weight_tonnes} onChange={(e) => set('weight_tonnes', e.target.value)} />)}
              {label(t('plan.packages'), <input className={field} inputMode="numeric" value={f.packages} onChange={(e) => set('packages', e.target.value.replace(/\D/g, ''))} />)}
            </div>
            {sec(t('plan.sec.consignee'))}
            <p className="-mt-2 text-xs text-muted">{t('priv.notice.collect')}</p>
            <div className="grid gap-4 sm:grid-cols-2">
              {label(t('plan.consignee'), <input className={field} required minLength={2} maxLength={160} value={f.consignee_name} onChange={(e) => set('consignee_name', e.target.value)} />)}
              <PhoneInput label={t('plan.consigneePhone')} required value={f.consignee_phone} onChange={(v) => set('consignee_phone', v)} />
              {label(t('plan.consigneeEmail'), <input className={field} type="email" required maxLength={160} value={f.consignee_email} onChange={(e) => set('consignee_email', e.target.value)} />)}
              {label(t('plan.consigneeLang'), <select className={field} value={f.consignee_language} onChange={(e) => set('consignee_language', e.target.value)}>{LANGUAGES.map(([v, name]) => <option key={v} value={v}>{name}</option>)}</select>)}
            </div>
          </>
        )}
        {editing && (
          <div className="space-y-3 rounded-xl border border-line p-3">
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <span><span className="text-muted">{t('lr.no')}</span> <b className="tabular-nums">{trip.lr_no}</b></span>
              <button type="button" onClick={() => void download(`/trips/${trip.id}/lr.pdf`, `${trip.trip_code}-LR.pdf`).catch(() => setError(t('lr.pdfFail')))} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium hover:border-accent hover:text-accent">{t('lr.download')}</button>
            </div>
            <DocSlots ownerType="trip" ownerId={trip.id} kinds={TRIP_DOCS} canEdit={canPlan} />
          </div>
        )}

        {error && (
          <p role="alert" className="flex items-start gap-2 rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn">
            <TriangleAlert size={16} className="mt-0.5 shrink-0" aria-hidden /> <span>{error}</span>
          </p>
        )}

        {confirmCancel ? (
          <div className="space-y-3 rounded-lg bg-bad-soft px-3 py-3 text-sm text-bad">
            <p>{t('plan.confirmCancel', { code: trip!.trip_code })}</p>
            <input aria-label={t('plan.cancelReason')} placeholder={t('plan.cancelReason')} maxLength={300} value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} className="h-11 w-full rounded-lg border border-bad bg-surface px-3.5 text-sm text-ink outline-none" />
            <div className="flex flex-wrap justify-end gap-3">
              <button type="button" onClick={() => setConfirmCancel(false)} className="rounded-lg border border-bad px-3 py-1.5">{t('plan.keep')}</button>
              <button type="button" disabled={busy || cancelReason.trim().length < 3} onClick={() => void cancel()} className="rounded-lg bg-bad px-3 py-1.5 text-on-solid disabled:opacity-50">{t('plan.cancelTrip')}</button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            {editing && !locked ? <button type="button" onClick={() => setConfirmCancel(true)} className="text-sm text-bad underline underline-offset-2">{t('plan.cancelTrip')}</button> : <span />}
            {!locked && (
              <div className="flex gap-2">
                {clash && <button type="button" disabled={busy} onClick={(e) => void save(e as unknown as FormEvent, true)} className="rounded-lg border border-warn px-4 py-2 text-sm font-medium text-warn">{t('plan.bookAnyway')}</button>}
                <button disabled={busy} className="rounded-lg bg-ink px-5 py-2 text-sm font-medium text-surface disabled:opacity-60">
                  {editing ? (busy ? t('plan.saving') : t('plan.save')) : (busy ? t('plan.creating') : t('plan.create'))}
                </button>
              </div>
            )}
          </div>
        )}
      </form>
      )}
    </dialog>
  )
}
