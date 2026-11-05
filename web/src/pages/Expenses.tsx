import { Check, Paperclip, TriangleAlert, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { api, ApiError, fetchBlob } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n, type Key } from '../lib/i18n'

interface Exp {
  id: string; category: string; amount: number; litres: number | null; odometer_km: number | null; note: string | null; status: string
  flags: string[]; trip_code: string | null; vehicle: string; driver: string; incurred_at: string; has_receipt: boolean; review_note: string | null
}
interface Pnl {
  window_days: number
  totals: { freight: number; expenses: number; margin: number; margin_pct: number | null }
  trips_without_costs: number
  by_category: Record<string, number>
  trips: { trip_id: string; trip_code: string; client: string; vehicle: string; destination: string; freight: number; expenses: number; pending: number; margin: number; margin_pct: number | null }[]
  vehicles: { vehicle: string; fills: number; km: number; litres: number; avg_kmpl: number | null; usual_kmpl: number | null; flagged: number; flags: string[] }[]
}
interface Settle {
  drivers: { driver_id: string; driver: string; advances: number; approved: number; pending: number; balance: number }[]
  recent_advances: { driver: string; amount: number; note: string | null; given_at: string }[]
}
type Tab = 'review' | 'profit' | 'fuel' | 'advances'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const catKey = (c: string) => `exp.cat.${c}` as Key

export default function Expenses() {
  const { t } = useI18n()
  const { user } = useAuth()
  const canDecide = user?.role === 'ops' || user?.role === 'billing' || user?.role === 'admin'
  const [tab, setTab] = useState<Tab>(canDecide ? 'review' : 'profit')
  const tabs: [Tab, Key][] = [...(canDecide ? [['review', 'exp.tabReview'] as [Tab, Key]] : []), ['profit', 'exp.tabProfit'], ['fuel', 'exp.tabFuel'], ['advances', 'exp.tabAdvances']]
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t('exp.title')}</h1>
        <p className="text-sm text-muted">{t('exp.sub')}</p>
      </div>
      <div className="flex gap-6 border-b border-line" role="tablist">
        {tabs.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={`border-b-2 px-1 pb-2 text-sm font-medium ${tab === k ? 'border-accent text-accent' : 'border-transparent text-muted hover:text-ink'}`}>{t(label)}</button>
        ))}
      </div>
      {tab === 'review' && <Review canDecide={canDecide} />}
      {tab === 'profit' && <Profit />}
      {tab === 'fuel' && <Fuel />}
      {tab === 'advances' && <Advances canGive={canDecide} />}
    </div>
  )
}

function FlagChips({ flags }: { flags: string[] }) {
  const { t } = useI18n()
  return <>{flags.map((f) => <span key={f} className="inline-flex items-center gap-1 rounded-full bg-warn-soft px-2.5 py-0.5 text-xs font-medium text-warn"><TriangleAlert size={12} aria-hidden />{t(`exp.flag.${f}` as Key)}</span>)}</>
}

function Review({ canDecide }: { canDecide: boolean }) {
  const { t, date } = useI18n()
  const [rows, setRows] = useState<Exp[] | null>(null)
  const [error, setError] = useState(false)
  const [rejecting, setRejecting] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [fail, setFail] = useState<string | null>(null)
  const [receipt, setReceipt] = useState<Exp | null>(null)
  const load = useCallback(() => api<Exp[]>('/expenses?status=pending').then(setRows).catch(() => setError(true)), [])
  useEffect(() => { void load() }, [load])

  async function decide(e: Exp, action: 'approve' | 'reject') {
    setFail(null)
    try {
      await api(`/expenses/${e.id}/decision`, { method: 'POST', body: JSON.stringify({ action, note: action === 'reject' ? reason : undefined }) })
      setRejecting(null); setReason('')
      await load()
    } catch (err) { setFail(err instanceof ApiError ? err.message : t('exp.decisionFail')) }
  }

  if (error) return <p className="text-bad">{t('exp.error')}</p>
  if (!rows) return <p className="text-muted">{t('common.loading')}</p>
  if (rows.length === 0) return <p className="rounded-xl border border-line py-16 text-center text-muted">{t('exp.emptyReview')}</p>
  return (
    <>
      {fail && <p role="alert" className="text-sm text-bad">{fail}</p>}
      <ul className="divide-y divide-line rounded-xl border border-line">
        {rows.map((e) => (
          <li key={e.id} className="space-y-3 px-5 py-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{t(catKey(e.category))}</span><FlagChips flags={e.flags} /></div>
                <div className="text-sm text-muted">{e.driver} · {e.vehicle}{e.trip_code ? ` · ${e.trip_code}` : ''} · {date(e.incurred_at, true)}</div>
                <div className="text-sm text-muted">
                  {[e.litres != null && t('exp.litres', { n: e.litres }), e.odometer_km != null && t('exp.odometer', { n: e.odometer_km.toLocaleString('en-IN') }), e.note].filter(Boolean).join(' · ')}
                </div>
              </div>
              <div className="text-right">
                <div className="text-xl font-semibold tabular-nums">{inr.format(e.amount)}</div>
                {e.has_receipt
                  ? <button onClick={() => setReceipt(e)} className="inline-flex items-center gap-1 text-sm text-accent underline underline-offset-2"><Paperclip size={14} aria-hidden /> {t('exp.viewReceipt')}</button>
                  : <span className="text-xs text-muted">{t('exp.noReceipt')}</span>}
              </div>
            </div>
            {canDecide && (rejecting === e.id ? (
              <form onSubmit={(ev: FormEvent) => { ev.preventDefault(); void decide(e, 'reject') }} className="flex flex-wrap items-center gap-2">
                <input autoFocus required minLength={3} maxLength={200} value={reason} onChange={(ev) => setReason(ev.target.value)} placeholder={t('exp.rejectReason')} aria-label={t('exp.rejectReason')}
                  className="min-w-64 flex-1 rounded-lg border border-line px-3 py-2 text-sm outline-none focus:border-accent" />
                <button className="rounded-lg bg-bad px-3 py-2 text-sm font-medium text-on-solid">{t('exp.confirmReject')}</button>
                <button type="button" onClick={() => setRejecting(null)} className="rounded-lg border border-line px-3 py-2 text-sm">{t('common.cancel')}</button>
              </form>
            ) : (
              <div className="flex gap-2">
                <button onClick={() => void decide(e, 'approve')} className="inline-flex items-center gap-1.5 rounded-lg bg-ok px-3 py-1.5 text-sm font-medium text-on-solid"><Check size={16} aria-hidden /> {t('exp.approve')}</button>
                <button onClick={() => { setRejecting(e.id); setReason('') }} className="inline-flex items-center gap-1.5 rounded-lg border border-bad px-3 py-1.5 text-sm font-medium text-bad"><X size={16} aria-hidden /> {t('exp.reject')}</button>
              </div>
            ))}
          </li>
        ))}
      </ul>
      {receipt && <ReceiptDialog exp={receipt} onClose={() => setReceipt(null)} />}
    </>
  )
}

function ReceiptDialog({ exp, onClose }: { exp: Exp; onClose: () => void }) {
  const { t } = useI18n()
  const ref = useRef<HTMLDialogElement>(null)
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    ref.current?.showModal()
    let u: string | null = null
    let alive = true
    fetchBlob(`/expenses/${exp.id}/receipt`).then((b) => { if (alive) { u = URL.createObjectURL(b); setUrl(u) } }).catch(() => undefined)
    return () => { alive = false; if (u) URL.revokeObjectURL(u) }
  }, [exp.id])
  return (
    <dialog ref={ref} onClose={onClose} aria-label={t('exp.receipt')} className="m-auto w-[min(34rem,94vw)] rounded-2xl border border-line p-0 shadow-xl backdrop:bg-black/30">
      <div className="space-y-3 p-5">
        <div className="flex items-center justify-between"><h2 className="font-semibold">{t('exp.receipt')} · {inr.format(exp.amount)}</h2><button onClick={() => ref.current?.close()} aria-label={t('common.close')} className="text-muted hover:text-ink"><X size={20} /></button></div>
        {url ? <img src={url} alt={t('exp.receipt')} className="max-h-[70vh] w-full rounded-lg object-contain" /> : <p className="text-muted">{t('common.loading')}</p>}
      </div>
    </dialog>
  )
}

function Profit() {
  const { t } = useI18n()
  const [days, setDays] = useState(90)
  const [d, setD] = useState<Pnl | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => { api<Pnl>(`/finance/pnl?days=${days}`).then(setD).catch(() => setError(true)) }, [days])
  if (error) return <p className="text-bad">{t('exp.error')}</p>
  if (!d) return <p className="text-muted">{t('common.loading')}</p>
  const tone = (m: number) => (m < 0 ? 'text-bad' : 'text-ok')
  const cats = Object.entries(d.by_category)
  const maxCat = Math.max(1, ...cats.map(([, v]) => v))
  return (
    <div className="space-y-6">
      <div className="flex gap-1" role="group" aria-label={t('dash.window')}>
        {[30, 90].map((v) => <button key={v} onClick={() => setDays(v)} aria-pressed={days === v} className={`rounded-lg px-3 py-1.5 text-sm ${days === v ? 'bg-accent-soft font-medium text-accent' : 'text-muted hover:text-ink'}`}>{t('exp.days', { n: v })}</button>)}
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-line p-5"><div className="text-sm text-muted">{t('exp.totalFreight')}</div><div className="mt-1 text-2xl font-semibold tabular-nums">{inr.format(d.totals.freight)}</div></div>
        <div className="rounded-xl border border-line p-5"><div className="text-sm text-muted">{t('exp.totalCosts')}</div><div className="mt-1 text-2xl font-semibold tabular-nums">{inr.format(d.totals.expenses)}</div></div>
        <div className="rounded-xl border border-line bg-accent-soft p-5"><div className="text-sm text-muted">{t('exp.totalMargin')}</div>
          <div className={`mt-1 text-2xl font-semibold tabular-nums ${tone(d.totals.margin)}`}>{inr.format(d.totals.margin)}{d.totals.margin_pct !== null && <span className="ml-2 text-base font-normal text-muted">{d.totals.margin_pct}%</span>}</div></div>
      </div>
      {cats.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-semibold">{t('exp.byCategory')}</h2>
          <ul className="space-y-2">
            {cats.map(([c, v]) => (
              <li key={c} className="grid grid-cols-[9rem_1fr_6rem] items-center gap-3 text-sm">
                <span className="text-muted">{t(catKey(c))}</span>
                <span className="h-3 rounded bg-wash"><span className="block h-3 rounded bg-accent" style={{ width: `${(v / maxCat) * 100}%` }} /></span>
                <span className="text-right tabular-nums">{inr.format(v)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="bg-wash text-muted"><tr>{(['exp.trip', 'exp.vehicle', 'exp.freight', 'exp.spent', 'exp.margin', 'exp.marginPct'] as const).map((h) => <th key={h} className="px-4 py-3 font-medium">{t(h)}</th>)}</tr></thead>
          <tbody>
            {d.trips.map((r) => (
              <tr key={r.trip_id} className="border-t border-line">
                <td className="px-4 py-3 font-medium">{r.trip_code}<div className="text-xs font-normal text-muted">{r.client} · {r.destination}</div></td>
                <td className="px-4 py-3">{r.vehicle}</td>
                <td className="px-4 py-3 tabular-nums">{inr.format(r.freight)}</td>
                <td className="px-4 py-3 tabular-nums">{inr.format(r.expenses)}{r.pending > 0 && <div className="text-xs text-warn">{t('exp.pending', { amt: inr.format(r.pending) })}</div>}</td>
                <td className={`px-4 py-3 font-medium tabular-nums ${tone(r.margin)}`}>{inr.format(r.margin)}</td>
                <td className="px-4 py-3 tabular-nums text-muted">{r.margin_pct ?? '—'}{r.margin_pct !== null && '%'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {d.trips_without_costs > 0 && <p role="note" className="rounded-lg bg-warn-soft px-4 py-2.5 text-sm text-warn">{t('exp.noCosts', { n: d.trips_without_costs, total: d.trips.length })}</p>}
      <p className="text-xs text-muted">{t('exp.profitNote')}</p>
    </div>
  )
}

function Fuel() {
  const { t } = useI18n()
  const [d, setD] = useState<Pnl | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => { api<Pnl>('/finance/pnl?days=365').then(setD).catch(() => setError(true)) }, [])
  if (error) return <p className="text-bad">{t('exp.error')}</p>
  if (!d) return <p className="text-muted">{t('common.loading')}</p>
  if (d.vehicles.length === 0) return <p className="rounded-xl border border-line py-16 text-center text-muted">{t('exp.fuelEmpty')}</p>
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="bg-wash text-muted"><tr>{(['exp.vehicle', 'exp.fills', 'exp.km', 'exp.avg', 'exp.usual', 'exp.flagged'] as const).map((h) => <th key={h} className="px-4 py-3 font-medium">{t(h)}</th>)}</tr></thead>
          <tbody>
            {d.vehicles.map((v) => (
              <tr key={v.vehicle} className="border-t border-line">
                <td className="px-4 py-3 font-medium">{v.vehicle}</td><td className="px-4 py-3 tabular-nums">{v.fills}</td><td className="px-4 py-3 tabular-nums">{v.km.toLocaleString('en-IN')}</td>
                <td className="px-4 py-3 tabular-nums">{v.avg_kmpl ?? '—'}</td><td className="px-4 py-3 tabular-nums">{v.usual_kmpl ?? '—'}</td>
                <td className="px-4 py-3"><div className="flex flex-wrap items-center gap-1.5">{v.flagged > 0 && <span className="font-medium text-warn tabular-nums">{v.flagged}</span>}<FlagChips flags={v.flags} /></div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">{t('exp.fuelNote')}</p>
    </div>
  )
}

function Advances({ canGive }: { canGive: boolean }) {
  const { t, date } = useI18n()
  const [s, setS] = useState<Settle | null>(null)
  const [drivers, setDrivers] = useState<{ id: string; name: string }[]>([])
  const [form, setForm] = useState({ driver_id: '', amount: '', note: '' })
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const load = useCallback(() => api<Settle>('/finance/settlement').then(setS).catch(() => setMsg({ ok: false, text: t('exp.error') })), [t])
  useEffect(() => {
    void load()
    if (canGive) api<{ drivers: { id: string; name: string }[] }>('/planning/refs').then((r) => { setDrivers(r.drivers); setForm((f) => ({ ...f, driver_id: r.drivers[0]?.id ?? '' })) }).catch(() => undefined)
  }, [load, canGive])

  async function give(e: FormEvent) {
    e.preventDefault()
    setMsg(null)
    try {
      await api('/finance/advances', { method: 'POST', body: JSON.stringify({ driver_id: form.driver_id, amount: form.amount, note: form.note || null }) })
      setForm((f) => ({ ...f, amount: '', note: '' }))
      setMsg({ ok: true, text: t('exp.adv.saved') })
      await load()
    } catch (err) { setMsg({ ok: false, text: err instanceof ApiError ? err.message : t('exp.decisionFail') }) }
  }

  if (!s) return <p className="text-muted">{msg?.text ?? t('common.loading')}</p>
  const field = 'w-full rounded-lg border border-line px-3 py-2 text-sm outline-none focus:border-accent'
  return (
    <div className="space-y-6">
      {canGive && (
        <form onSubmit={give} className="grid items-end gap-3 rounded-xl border border-line p-4 sm:grid-cols-[1fr_9rem_1fr_auto]">
          <label className="space-y-1 text-sm"><span className="text-muted">{t('exp.driver')}</span>
            <select className={field} value={form.driver_id} onChange={(e) => setForm({ ...form, driver_id: e.target.value })}>{drivers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
          <label className="space-y-1 text-sm"><span className="text-muted">{t('exp.adv.amount')}</span>
            <input className={field} required inputMode="decimal" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value.replace(/[^\d.]/g, '') })} /></label>
          <label className="space-y-1 text-sm"><span className="text-muted">{t('exp.adv.note')}</span>
            <input className={field} maxLength={200} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
          <button className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-surface">{t('exp.adv.save')}</button>
        </form>
      )}
      {msg && <p role={msg.ok ? 'status' : 'alert'} className={`text-sm ${msg.ok ? 'text-ok' : 'text-bad'}`}>{msg.text}</p>}
      {s.drivers.length === 0 ? <p className="rounded-xl border border-line py-12 text-center text-muted">{t('exp.adv.none')}</p> : (
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-wash text-muted"><tr>{(['exp.driver', 'exp.adv.advances', 'exp.adv.spent', 'exp.status.pending', 'exp.adv.balance'] as const).map((h) => <th key={h} className="px-4 py-3 font-medium">{t(h)}</th>)}</tr></thead>
            <tbody>
              {s.drivers.map((r) => (
                <tr key={r.driver_id} className="border-t border-line">
                  <td className="px-4 py-3 font-medium">{r.driver}</td><td className="px-4 py-3 tabular-nums">{inr.format(r.advances)}</td><td className="px-4 py-3 tabular-nums">{inr.format(r.approved)}</td>
                  <td className="px-4 py-3 tabular-nums text-muted">{inr.format(r.pending)}</td>
                  <td className={`px-4 py-3 font-medium tabular-nums ${r.balance < 0 ? 'text-bad' : ''}`}>{inr.format(Math.abs(r.balance))}{r.balance < 0 && <span className="ml-1.5 text-xs font-normal">{t('exp.adv.owed')}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {s.recent_advances.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-semibold">{t('exp.adv.recent')}</h2>
          <ul className="divide-y divide-line rounded-xl border border-line text-sm">
            {s.recent_advances.map((a, i) => <li key={i} className="flex justify-between gap-3 px-4 py-2.5"><span>{a.driver}{a.note ? ` · ${a.note}` : ''}<span className="ml-2 text-muted">{date(a.given_at, true)}</span></span><span className="tabular-nums">{inr.format(a.amount)}</span></li>)}
          </ul>
        </section>
      )}
      <p className="text-xs text-muted">{t('exp.adv.note2')}</p>
    </div>
  )
}
