import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { btnGhost, btnPrimary, Field, FormModal, inputCls } from './setup/ui'

interface Req {
  id: string; reference: string; kind: 'access' | 'correction' | 'erasure' | 'consent' | 'complaint'; name: string | null; phone: string; message: string | null
  source: 'public' | 'office'; status: 'open' | 'done' | 'refused'; outcome: string | null; due_at: string; closed_at: string | null; created_at: string; overdue: boolean
}
interface Held {
  trips: { trip_code: string; lr_no: string; route: string; consignee_name: string | null; consignee_email: string | null }[]
  requests: { reference: string; company: string; contact_name: string; email: string | null; status: string }[]
  drivers: { name: string; email: string | null; licence_no: string | null }[]
}
const KINDS = ['access', 'correction', 'erasure', 'consent', 'complaint'] as const

/** The privacy officer's desk (admin and MD): the register of people's requests about their own data, what is held under a number, erasing it, closing with what was done. */
export default function OfficePrivacy() {
  const { t, date } = useI18n()
  const [rows, setRows] = useState<Req[] | null>(null)
  const [error, setError] = useState(false)
  const [tab, setTab] = useState<'open' | 'closed'>('open')
  const [open, setOpen] = useState<Req | null>(null)
  const [adding, setAdding] = useState(false)
  const load = useCallback(() => { api<Req[]>('/privacy/requests').then(setRows).catch(() => setError(true)) }, [])
  useEffect(() => { load() }, [load])
  const shown = (rows ?? []).filter((r) => (tab === 'open') === (r.status === 'open'))

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">{t('priv.o.title')}</h1>
          <p className="max-w-2xl text-sm text-muted">{t('priv.o.sub')}</p>
        </div>
        <button className={btnPrimary} onClick={() => setAdding(true)}>{t('priv.o.log')}</button>
      </header>
      <div role="tablist" className="flex gap-1 border-b border-line">
        {(['open', 'closed'] as const).map((k) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${tab === k ? 'border-ink' : 'border-transparent text-muted'}`}>{t(k === 'open' ? 'priv.o.open' : 'priv.o.closed')}</button>
        ))}
      </div>
      {error && <p role="alert" className="text-bad">{t('priv.o.error')}</p>}
      {rows && shown.length === 0 && <p className="text-muted">{t('priv.o.none')}</p>}
      <ul className="divide-y divide-line rounded-xl border border-line">
        {shown.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-sm">
            <b className="font-mono tabular-nums">{r.reference}</b>
            <span className="font-medium">{t(`priv.k.${r.kind}`)}</span>
            <span className="text-muted">{r.name ? `${r.name} · ` : ''}{r.phone} · {t(`priv.o.source.${r.source}`)}</span>
            <span className="ml-auto flex items-center gap-3">
              {r.status === 'open'
                ? <span className={r.overdue ? 'font-medium text-bad' : 'text-muted'}>{r.overdue ? t('priv.o.overdue') : t('priv.o.due', { date: date(r.due_at) })}</span>
                : <span className="text-muted">{r.outcome}</span>}
              {r.status === 'open' && <button className={btnGhost} onClick={() => setOpen(r)}>{t('priv.o.lookup')}</button>}
            </span>
            {r.message && <p className="basis-full text-muted">{r.message}</p>}
          </li>
        ))}
      </ul>
      {open && <Handle req={open} onClose={() => { setOpen(null); load() }} />}
      {adding && <Log onClose={() => { setAdding(false); load() }} />}
    </div>
  )
}

function Handle({ req, onClose }: { req: Req; onClose: () => void }) {
  const { t } = useI18n()
  const [held, setHeld] = useState<Held | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [outcome, setOutcome] = useState<'done' | 'refused'>('done')
  const [note, setNote] = useState('')
  useEffect(() => { api<Held>('/privacy/access', { method: 'POST', body: JSON.stringify({ phone: req.phone }) }).then(setHeld).catch(() => setMsg(t('priv.o.error'))) }, [req.phone, t])
  const nothing = held && !held.trips.length && !held.requests.length && !held.drivers.length

  async function erase() {
    if (!window.confirm(t('priv.o.eraseAsk'))) return
    try {
      const r = await api<{ trips: number; requests: number; drivers: number }>('/privacy/erase', { method: 'POST', body: JSON.stringify({ phone: req.phone }) })
      setMsg(t('priv.o.erased', { trips: String(r.trips), requests: String(r.requests), drivers: String(r.drivers) }))
      setNote(t('priv.o.erased', { trips: String(r.trips), requests: String(r.requests), drivers: String(r.drivers) }))
      setHeld({ trips: [], requests: [], drivers: [] })
    } catch (e) { setMsg(e instanceof ApiError ? e.message : t('priv.o.error')) }
  }
  return (
    <FormModal title={`${req.reference} · ${t(`priv.k.${req.kind}`)}`} wide onClose={onClose} submitLabel={t('priv.o.close')}
      onSubmit={async () => { await api(`/privacy/requests/${req.id}/close`, { method: 'POST', body: JSON.stringify({ outcome, note }) }); onClose() }}>
      {req.message && <p className="rounded-lg bg-wash px-3 py-2 text-sm">{req.message}</p>}
      <section className="space-y-2 text-sm">
        {nothing && <p className="text-muted">{t('priv.o.nothing')}</p>}
        {held && held.trips.length > 0 && <div><b>{t('priv.o.trips')}</b><ul className="mt-1 text-muted">{held.trips.map((x) => <li key={x.trip_code}>{x.trip_code} · {x.lr_no} · {x.route} · {x.consignee_name} {x.consignee_email}</li>)}</ul></div>}
        {held && held.requests.length > 0 && <div><b>{t('priv.o.reqs')}</b><ul className="mt-1 text-muted">{held.requests.map((x) => <li key={x.reference}>{x.reference} · {x.company} · {x.contact_name} {x.email}</li>)}</ul></div>}
        {held && held.drivers.length > 0 && <div><b>{t('priv.o.drivers')}</b><ul className="mt-1 text-muted">{held.drivers.map((x) => <li key={x.licence_no ?? x.name}>{x.name} · {x.licence_no} {x.email}</li>)}</ul></div>}
        {msg && <p role="status" className="font-medium text-ok">{msg}</p>}
        {held && !nothing && <button type="button" className={btnGhost} onClick={() => void erase()}>{t('priv.o.erase')}</button>}
      </section>
      <Field label={t('priv.o.note')}><textarea className={`${inputCls} h-20`} required minLength={3} maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      <div className="flex gap-4 text-sm">
        {(['done', 'refused'] as const).map((k) => <label key={k} className="flex items-center gap-2"><input type="radio" name="outcome" checked={outcome === k} onChange={() => setOutcome(k)} /> {t(k === 'done' ? 'priv.o.done' : 'priv.o.refused')}</label>)}
      </div>
    </FormModal>
  )
}

function Log({ onClose }: { onClose: () => void }) {
  const { t } = useI18n()
  const [f, setF] = useState({ kind: 'access' as (typeof KINDS)[number], phone: '', name: '', message: '' })
  return (
    <FormModal title={t('priv.o.log')} onClose={onClose} onSubmit={async () => { await api('/privacy/requests', { method: 'POST', body: JSON.stringify({ ...f, name: f.name || null, message: f.message || null }) }); onClose() }}>
      <Field label={t('priv.kind')}><select className={inputCls} value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value as typeof f.kind })}>{KINDS.map((k) => <option key={k} value={k}>{t(`priv.k.${k}`)}</option>)}</select></Field>
      <Field label={t('priv.phone')}><input className={inputCls} required inputMode="numeric" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
      <Field label={t('priv.name')}><input className={inputCls} maxLength={120} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
      <Field label={t('priv.message')}><textarea className={`${inputCls} h-20`} maxLength={500} value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} /></Field>
    </FormModal>
  )
}
