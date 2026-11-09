import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { FilterBar, NoMatch } from '../components/FilterBar'
import { hit, useFilters } from '../lib/filters'
import { useI18n } from '../lib/i18n'
import { btnGhost, btnPrimary, Facts, Field, FormModal, inputCls, Modal } from './setup/ui'
import { useLive } from '../lib/live'

interface Req {
  id: string; reference: string; status: 'new' | 'accepted' | 'booked' | 'declined'; created_at: string; company_name: string; contact_name: string; phone: string
  email: string | null; gstin: string | null; origin: string; destination: string; material: string; weight_tonnes: number | null; truck_type: string | null
  pickup_date: string; notes: string | null; client_id: string | null; client: string | null; trip_code: string | null; quote_amount: number | null; reply: string | null
  quote_accepted_at: string | null; quote_accepted_via: 'online' | 'phone' | null; declined_by: 'office' | 'client' | null; decline_reason: string | null; decline_seen: boolean
  decided_at: string | null; quote_sent_at: string | null
}
const FILTERS = { q: '' }
const TONE = { new: 'bg-warn-soft text-warn', accepted: 'bg-accent-soft text-accent', booked: 'bg-ok-soft text-ok', declined: 'bg-wash text-muted' } as const

/** Companies that asked for transport. Ops accepts (and onboards the company as a client in the same step), declines with a reason, or books the trip. */
export default function Requests() {
  const { t, date } = useI18n()
  const { user } = useAuth()
  const nav = useNavigate()
  const canAct = user?.role === 'ops' || user?.role === 'admin'
  const [state, setState] = useState<'open' | 'declined' | 'all'>('open')
  const [rows, setRows] = useState<Req[] | null>(null)
  const [error, setError] = useState(false)
  const [accept, setAccept] = useState<Req | null>(null)
  const [decline, setDecline] = useState<Req | null>(null)
  const [view, setView] = useState<Req | null>(null)
  const [requote, setRequote] = useState<Req | null>(null)
  const load = useCallback(() => { api<Req[]>(`/requests?state=${state}`).then(setRows).catch(() => setError(true)) }, [state])
  const phoneYes = async (r: Req) => { await api(`/requests/${r.id}/quote-confirmed`, { method: 'POST', body: JSON.stringify({}) }).catch(() => undefined); load() }
  const seen = async (r: Req) => { await api(`/requests/${r.id}/seen`, { method: 'POST' }).catch(() => undefined); load() }
  useEffect(() => { load() }, [load])
  useLive(['requests'], load)
  const { values: f, set, clear, active } = useFilters(FILTERS)
  const shownRows = (rows ?? []).filter((r) => hit(f.q, r.company_name, r.reference, r.contact_name, r.phone, r.origin, r.destination, r.material, r.client, r.trip_code))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-3xl font-semibold tracking-tight">{t('req.o.title')}</h1><p className="text-sm text-muted">{t('req.o.sub')}</p></div>
        <div role="tablist" className="flex gap-1 rounded-lg border border-line p-1 text-sm">
          {(['open', 'declined', 'all'] as const).map((x) => <button key={x} role="tab" aria-selected={state === x} onClick={() => setState(x)} className={`rounded-md px-3 py-1 ${state === x ? 'bg-accent-soft font-medium text-accent' : 'text-muted'}`}>{t(`req.o.${x}`)}</button>)}
        </div>
      </div>
      {rows && rows.length > 0 && <FilterBar q={f.q} onQ={(v) => set('q', v)} placeholder={t('filter.requests')} shown={shownRows.length} total={rows.length} active={active} onClear={clear} />}
      {error ? <p className="text-bad">{t('req.o.loadFail')}</p> : !rows ? <p className="text-muted">{t('common.loading')}</p> : rows.length === 0 ? <p className="rounded-xl border border-line px-4 py-8 text-center text-muted">{t('req.o.none')}</p> : shownRows.length === 0 ? <NoMatch onClear={clear} /> : (
        <ul className="divide-y divide-line rounded-xl border border-line">
          {shownRows.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-4">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{r.company_name} <span className="ml-1 text-xs font-normal tabular-nums text-muted">{r.reference}</span></p>
                <p className="text-sm text-muted">{r.origin} → {r.destination} · {r.material}{r.weight_tonnes ? ` · ${r.weight_tonnes} t` : ''} · {r.pickup_date}</p>
                <p className="text-xs text-muted">{t('req.o.received')} {date(r.created_at, true)}</p>
                {r.status === 'declined' && <p className="text-xs font-medium text-bad">{t(r.declined_by === 'client' ? 'req.o.byClient' : 'req.o.byOffice')} · {t('req.o.why', { why: r.decline_reason ?? t('req.o.noReason') })}{r.declined_by === 'client' && r.quote_amount !== null ? ` · ₹${r.quote_amount.toLocaleString('en-IN')}` : ''}</p>}
                {r.status === 'accepted' && r.quote_amount !== null && <p className={`text-xs font-medium ${r.quote_accepted_at ? 'text-ok' : 'text-warn'}`}>{r.quote_accepted_at ? t(r.quote_accepted_via === 'phone' ? 'req.o.quotePhone' : 'req.o.quoteOnline') : t('req.o.waitingQuote')}</p>}
              </div>
              <span className={`rounded-full px-2.5 py-0.5 text-xs ${TONE[r.status]}`}>{t(`req.status.${r.status}`)}</span>
              <div className="flex flex-wrap gap-2">
                <button onClick={() => setView(r)} className={btnGhost}>{t('onb.details')}</button>
                {canAct && r.status === 'new' && <button onClick={() => setAccept(r)} className={btnPrimary}>{t('req.o.accept')}</button>}
                {canAct && (r.status === 'new' || r.status === 'accepted') && <button onClick={() => setDecline(r)} className={btnGhost}>{t('req.o.decline')}</button>}
                {canAct && r.status === 'accepted' && r.quote_amount !== null && !r.quote_accepted_at && <button onClick={() => void phoneYes(r)} className={btnGhost}>{t('req.o.phoneYes')}</button>}
                {canAct && ((r.status === 'accepted' && r.quote_amount !== null && !r.quote_accepted_at) || (r.status === 'declined' && r.declined_by === 'client')) && <button onClick={() => setRequote(r)} className={btnGhost}>{t('req.o.requote')}</button>}
                {canAct && r.status === 'declined' && r.declined_by === 'client' && !r.decline_seen && <button onClick={() => void seen(r)} className={btnPrimary}>{t('req.o.seen')}</button>}
                {canAct && r.status === 'accepted' && (r.quote_amount === null || r.quote_accepted_at) && <button onClick={() => nav(`/office/planning?request=${r.id}`)} className={btnPrimary}>{t('req.o.book')}</button>}
              </div>
            </li>
          ))}
        </ul>
      )}
      {view && (
        <Modal title={`${view.company_name} · ${view.reference}`} onClose={() => setView(null)} wide>
          <Facts rows={[
            [t('req.contact'), view.contact_name], [t('req.phone'), view.phone], [t('req.email'), view.email], [t('req.gstin'), view.gstin],
            [t('req.route'), `${view.origin} → ${view.destination}`], [t('req.material'), [view.material, view.weight_tonnes ? `${view.weight_tonnes} t` : null].filter(Boolean).join(' · ')],
            [t('req.truck'), view.truck_type], [t('req.pickup'), view.pickup_date], [t('req.o.client'), view.client], [t('req.o.trip'), view.trip_code],
            [t('req.quote'), view.quote_amount !== null ? `₹${view.quote_amount.toLocaleString('en-IN')}` : null], [t('req.reply'), view.reply], [t('req.o.notes'), view.notes],
          ]} />
          <h3 className="pt-2 text-sm font-semibold">{t('req.o.history')}</h3>
          <ul className="space-y-1 text-sm">
            <li>{date(view.created_at, true)} · {t('req.o.h.received')}</li>
            {view.quote_sent_at && view.quote_amount !== null && <li>{date(view.quote_sent_at, true)} · {t('req.o.h.quoted', { amount: `₹${view.quote_amount.toLocaleString('en-IN')}` })}</li>}
            {view.quote_accepted_at && <li>{date(view.quote_accepted_at, true)} · {t('req.o.h.yes', { how: view.quote_accepted_via ?? '' })}</li>}
            {view.status === 'declined' && view.decided_at && <li>{date(view.decided_at, true)} · {t(view.declined_by === 'client' ? 'req.o.h.no' : 'req.o.h.office', { why: view.decline_reason ?? '' })}</li>}
            {view.trip_code && <li>{t('req.o.h.booked', { trip: view.trip_code })}</li>}
          </ul>
          <div className="flex justify-end"><button onClick={() => setView(null)} className={btnPrimary}>{t('setup.close')}</button></div>
        </Modal>
      )}
      {requote && <RequoteDialog req={requote} onClose={() => setRequote(null)} onDone={() => { setRequote(null); load() }} />}
      {accept && <AcceptDialog req={accept} onClose={() => setAccept(null)} onDone={() => { setAccept(null); load() }} />}
      {decline && <DeclineDialog req={decline} onClose={() => setDecline(null)} onDone={() => { setDecline(null); load() }} />}
    </div>
  )
}

function AcceptDialog({ req, onClose, onDone }: { req: Req; onClose: () => void; onDone: () => void }) {
  const { t } = useI18n()
  const [clients, setClients] = useState<{ id: string; name: string; is_active: boolean }[]>([])
  const [f, setF] = useState({ client_id: req.client_id ?? '', billing_cycle: 'weekly', quote_amount: '', note: '' })
  useEffect(() => { api<typeof clients>('/setup/clients').then(setClients).catch(() => undefined) }, [])
  async function save() {
    await api(`/requests/${req.id}/accept`, { method: 'POST', body: JSON.stringify({ client_id: f.client_id || null, billing_cycle: f.billing_cycle, quote_amount: f.quote_amount || null, note: f.note || null }) })
    onDone()
  }
  return (
    <FormModal title={t('req.a.title', { ref: req.reference })} onClose={onClose} onSubmit={save} submitLabel={t('req.a.go')}>
      <Field label={t('req.a.client')}>
        <select className={inputCls} value={f.client_id} onChange={(e) => setF({ ...f, client_id: e.target.value })}>
          <option value="">{t('req.a.newClient', { company: req.company_name })}</option>
          {clients.filter((c) => c.is_active).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </Field>
      {!f.client_id && (
        <Field label={t('setup.client.cycle')}>
          <select className={inputCls} value={f.billing_cycle} onChange={(e) => setF({ ...f, billing_cycle: e.target.value })}>
            {(['weekly', 'fortnightly', 'monthly', 'per_trip'] as const).map((c) => <option key={c} value={c}>{t(`setup.cycle.${c}`)}</option>)}
          </select>
        </Field>
      )}
      <Field label={t('req.a.quote')}><input className={inputCls} inputMode="decimal" value={f.quote_amount} onChange={(e) => setF({ ...f, quote_amount: e.target.value })} /></Field>
      <Field label={t('req.a.note')}><input className={inputCls} maxLength={300} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
    </FormModal>
  )
}

function DeclineDialog({ req, onClose, onDone }: { req: Req; onClose: () => void; onDone: () => void }) {
  const { t } = useI18n()
  const [reason, setReason] = useState('')
  async function save() {
    await api(`/requests/${req.id}/decline`, { method: 'POST', body: JSON.stringify({ reason }) })
    onDone()
  }
  return (
    <FormModal title={t('req.d.title', { ref: req.reference })} onClose={onClose} onSubmit={save} submitLabel={t('req.d.go')}>
      <Field label={t('req.d.reason')}><input className={inputCls} required minLength={3} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
    </FormModal>
  )
}

function RequoteDialog({ req, onClose, onDone }: { req: Req; onClose: () => void; onDone: () => void }) {
  const { t } = useI18n()
  const [f, setF] = useState({ quote_amount: '', note: '' })
  async function save() {
    await api(`/requests/${req.id}/requote`, { method: 'POST', body: JSON.stringify({ quote_amount: f.quote_amount, note: f.note || null }) })
    onDone()
  }
  return (
    <FormModal title={t('req.o.requoteTitle', { ref: req.reference })} onClose={onClose} onSubmit={save} submitLabel={t('req.o.requoteGo')}>
      {req.decline_reason && <p className="text-sm text-muted">{t('req.o.why', { why: req.decline_reason })}</p>}
      <Field label={t('req.a.quote')}><input className={inputCls} required inputMode="decimal" value={f.quote_amount} onChange={(e) => setF({ ...f, quote_amount: e.target.value })} /></Field>
      <Field label={t('req.a.note')}><input className={inputCls} maxLength={300} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
    </FormModal>
  )
}
