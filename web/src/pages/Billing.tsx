import { Link } from 'react-router-dom'
import { FileCode2, FileText, Sheet } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { PaymentsDialog } from '../components/PaymentsDialog'
import { api, ApiError, download, type ClaimRow, type Invoice, type QueueGroup } from '../lib/api'
import { useI18n } from '../lib/i18n'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const waiting = (iso: string | null) => (iso ? Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)) : 0)

export default function Billing() {
  const { t } = useI18n()
  const [tab, setTab] = useState<'ready' | 'invoices' | 'claims'>('ready')
  const [claims, setClaims] = useState<ClaimRow[] | null>(null)
  const [groups, setGroups] = useState<QueueGroup[] | null>(null)
  const [invoices, setInvoices] = useState<Invoice[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [g, i, c] = await Promise.all([api<QueueGroup[]>('/billing/queue'), api<Invoice[]>('/billing/invoices'), api<ClaimRow[]>('/billing/claims')])
      setGroups(g)
      setInvoices(i)
      setClaims(c)
    } catch {
      setError(t('bill.error'))
    }
  }, [t])
  useEffect(() => { void load() }, [load])

  const tabBtn = (k: typeof tab, label: string, n?: number) => (
    <button onClick={() => setTab(k)} className={`border-b-2 px-1 pb-2 text-sm font-medium ${tab === k ? 'border-ink text-ink' : 'border-transparent text-muted hover:text-ink'}`}>
      {label}{n ? <span className="ml-1.5 text-xs text-muted">{n}</span> : null}
    </button>
  )

  if (error) return <p className="text-bad">{error}</p>
  if (!groups || !invoices || !claims) return <p className="text-muted">{t('common.loading')}</p>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">{t('bill.title')}</h1>
        <p className="text-sm text-muted">{t('bill.sub')}</p>
      </div>
      <div className="flex gap-6 border-b border-line">
        {tabBtn('ready', t('bill.tabReady'), groups.reduce((n, g) => n + g.trips.length, 0))}
        {tabBtn('invoices', t('bill.tabInvoices'), invoices.length)}
        {tabBtn('claims', t('bill.tabClaims'), claims.length)}
      </div>
      {tab === 'ready'
        ? <Ready groups={groups} onCreated={async () => { await load(); setTab('invoices') }} onStale={load} />
        : tab === 'invoices' ? <Invoices invoices={invoices} onExported={load} />
          : <Claims claims={claims} onDecided={load} />}
    </div>
  )
}

function Ready({ groups, onCreated, onStale }: { groups: QueueGroup[]; onCreated: () => Promise<void>; onStale: () => Promise<void> }) {
  const { t } = useI18n()
  if (groups.length === 0) {
    return <div className="rounded-2xl border border-line py-20 text-center text-muted">{t('bill.emptyReady')}</div>
  }
  return <div className="space-y-6">{groups.map((g) => <Group key={`${g.client_id}-${g.period_key}`} group={g} onCreated={onCreated} onStale={onStale} />)}</div>
}

function Group({ group, onCreated, onStale }: { group: QueueGroup; onCreated: () => Promise<void>; onStale: () => Promise<void> }) {
  const { t: tx, date } = useI18n()
  const [picked, setPicked] = useState<Set<string>>(() => new Set(group.trips.map((t) => t.id)))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const chosen = group.trips.filter((x) => picked.has(x.id))
  const sum = chosen.reduce((n, x) => n + x.freight_amount, 0)

  const toggle = (id: string) => setPicked((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n })

  async function create() {
    setBusy(true)
    setError(null)
    try {
      await api('/billing/invoices', { method: 'POST', body: JSON.stringify({ trip_ids: chosen.map((x) => x.id) }) })
      await onCreated()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : tx('bill.createFail'))
      if (e instanceof ApiError && e.status === 409) await onStale() // someone else billed these - refresh
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-line">
      <header className="flex flex-wrap items-baseline justify-between gap-2 bg-wash px-5 py-3">
        <div>
          <span className="font-semibold">{group.client}</span>
          <span className="ml-3 text-sm text-muted">{group.period_label} · {group.billing_cycle}</span>
        </div>
        <span className="text-sm text-muted">{tx('bill.oldest', { n: waiting(group.oldest_verified_at) })}</span>
      </header>
      <table className="w-full text-left text-sm">
        <tbody>
          {group.trips.map((x) => (
            <tr key={x.id} className="border-t border-line">
              <td className="w-10 py-3 pl-5"><input type="checkbox" checked={picked.has(x.id)} onChange={() => toggle(x.id)} aria-label={tx('bill.include', { code: x.trip_code })} /></td>
              <td className="px-3 py-3 font-medium">{x.trip_code}<div className="text-xs font-normal text-muted">{x.lr_no} · EWB {x.eway_bill_no} · <Link to={`/office/review/${x.id}`} className="font-medium underline hover:text-accent">{tx('trips.viewPod')}</Link></div></td>
              <td className="px-3 py-3">{x.destination}</td>
              <td className="px-3 py-3 text-muted">{x.delivered_at ? date(x.delivered_at) : '—'}</td>
              <td className="py-3 pr-5 text-right tabular-nums">{inr.format(x.freight_amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-5 py-3">
        <div className="text-sm"><span className="text-muted">{tx('bill.count', { a: chosen.length, b: group.trips.length, unit: tx(group.trips.length === 1 ? 'bill.trip' : 'bill.trips') })} · </span><span className="font-semibold tabular-nums">{inr.format(sum)}</span></div>
        {error && <span role="alert" className="text-sm text-bad">{error}</span>}
        <button disabled={busy || chosen.length === 0} onClick={() => void create()}
          className="h-10 rounded-lg bg-ink px-5 text-sm font-medium text-surface hover:opacity-90 disabled:opacity-50">
          {busy ? tx('bill.creating') : tx('bill.create')}
        </button>
      </footer>
    </section>
  )
}

function Invoices({ invoices, onExported }: { invoices: Invoice[]; onExported: () => Promise<void> }) {
  const { t, date } = useI18n()
  const [error, setError] = useState<string | null>(null)
  const [paying, setPaying] = useState<Invoice | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const markSent = async (inv: Invoice) => {
    setError(null)
    try { await api(`/billing/invoices/${inv.id}/sent`, { method: 'POST' }); await onExported() } catch { setError(t('sh.failed')) }
  }
  const send = async (inv: Invoice) => {
    setError(null); setNote(null)
    try { await api(`/billing/invoices/${inv.id}/send`, { method: 'POST' }); setNote(t('bill.sentOk', { no: inv.invoice_no })); await onExported() }
    catch (e) { setError(e instanceof ApiError ? e.message : t('sh.failed')) }
  }
  const get = async (inv: Invoice, kind: 'pdf' | 'tally' | 'csv') => {
    setError(null)
    try {
      await download(`/billing/invoices/${inv.id}/${kind}`, `${inv.invoice_no}.${kind === 'tally' ? 'xml' : kind}`)
      await onExported()
    } catch {
      setError(t('bill.dlFail'))
    }
  }
  if (invoices.length === 0) return <div className="rounded-2xl border border-line py-20 text-center text-muted">{t('bill.emptyInvoices')}</div>
  const btn = 'inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-ink hover:border-ink hover:bg-wash'
  return (
    <div className="space-y-3">
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      {note && <p role="status" className="text-sm text-ok">{note}</p>}
      <div className="overflow-x-auto rounded-2xl border border-line">
        <table className="w-full min-w-[860px] text-left text-sm">
          <thead className="bg-wash text-muted">
            <tr>{(['bill.invoice', 'bill.client', 'bill.period', 'bill.tripsCol', 'bill.total', 'bill.status', 'bill.exported', 'bill.download'] as const).map((h) => <th key={h} className="px-4 py-3 font-medium">{t(h)}</th>)}</tr>
          </thead>
          <tbody>
            {invoices.map((i) => (
              <tr key={i.id} className="border-t border-line">
                <td className="px-4 py-3 font-medium">{i.invoice_no}<div className="text-xs font-normal text-muted">{date(i.created_at)}</div></td>
                <td className="px-4 py-3">{i.client}</td>
                <td className="px-4 py-3 text-muted">{i.period_label ?? '—'}</td>
                <td className="px-4 py-3 tabular-nums">{i.trip_count}</td>
                <td className="px-4 py-3 tabular-nums">{inr.format(i.total)}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${i.paid_at ? 'bg-ok-soft text-ok' : i.paid_amount > 0 ? 'bg-warn-soft text-warn' : i.sent_at ? 'bg-accent-soft text-accent' : 'bg-wash text-muted'}`}>
                    {t(i.paid_at ? 'bill.st.paid' : i.paid_amount > 0 ? 'bill.st.part' : i.sent_at ? 'bill.st.sent' : 'bill.st.draft')}
                  </span>
                  {i.pending_claims > 0 && <span className="ml-1.5 rounded-full bg-warn-soft px-2 py-0.5 text-xs font-medium text-warn">{t('bill.claimsBadge', { n: i.pending_claims })}</span>}
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                    {!i.sent_at ? (
                      <>
                        <button disabled={!i.client_has_email} className="rounded-lg bg-ink px-2.5 py-1 text-xs font-medium text-surface hover:opacity-90 disabled:opacity-50" title={i.client_has_email ? t('bill.sendHelp') : t('bill.noEmail')} onClick={() => void send(i)}>{t('bill.send')}</button>
                        <button className="text-xs font-medium underline hover:text-accent" title={t('bill.markSentHelp')} onClick={() => void markSent(i)}>{t('bill.markSent')}</button>
                        {!i.client_has_email && <span className="text-xs text-muted">{t('bill.noEmail')}</span>}
                      </>
                    ) : (
                      <>
                        <button className="text-xs font-medium underline hover:text-accent" onClick={() => setPaying(i)}>{t('bill.pay')}</button>
                        {i.client_has_email && !i.paid_at && <button className="text-xs text-muted underline hover:text-accent" onClick={() => void send(i)}>{t('bill.sendAgain')}</button>}
                      </>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3">{i.exported_at ? <span className="text-ok">{date(i.exported_at)}</span> : <span className="text-muted">{t('bill.notYet')}</span>}</td>
                <td className="px-4 py-3">
                  <div className="flex gap-2">
                    <button className={btn} onClick={() => void get(i, 'pdf')}><FileText size={14} aria-hidden /> PDF</button>
                    <button className={btn} onClick={() => void get(i, 'tally')}><FileCode2 size={14} aria-hidden /> Tally</button>
                    <button className={btn} onClick={() => void get(i, 'csv')}><Sheet size={14} aria-hidden /> CSV</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">{t('bill.note')}</p>
      {paying && <PaymentsDialog invoice={paying} onClose={() => setPaying(null)} onChanged={() => void onExported()} />}
    </div>
  )
}

/** What clients say they have paid, waiting for someone to look at the bank. Confirming records the payment (the invoice may then be paid); turning it down says why, and the client reads that. */
function Claims({ claims, onDecided }: { claims: ClaimRow[]; onDecided: () => Promise<void> }) {
  const { t, date } = useI18n()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [rejecting, setRejecting] = useState<string | null>(null)
  const [why, setWhy] = useState('')
  const [amounts, setAmounts] = useState<Record<string, string>>({})
  async function run(id: string, path: 'confirm' | 'reject', body?: object) {
    setBusy(id); setError(null)
    try { await api(`/billing/claims/${id}/${path}`, { method: 'POST', body: body ? JSON.stringify(body) : undefined }); setRejecting(null); setWhy(''); await onDecided() }
    catch (e) { setError(e instanceof ApiError ? e.message : t('sh.failed')) }
    finally { setBusy(null) }
  }
  if (claims.length === 0) return <div className="rounded-2xl border border-line py-20 text-center text-muted">{t('bill.claimEmpty')}</div>
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">{t('bill.claimHelp')}</p>
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      <ul className="space-y-3">
        {claims.map((c) => (
          <li key={c.id} className="space-y-3 rounded-2xl border border-line p-4 text-sm">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p><span className="font-semibold">{c.client}</span> · {c.invoice_no}</p>
              <p className="text-muted">{t('bill.claimOn', { when: date(c.created_at, true) })} · {t(`bill.via.${c.via}` as const)}</p>
            </div>
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div><dt className="text-muted">{t('bill.claimSaid')}</dt><dd className="font-semibold tabular-nums">{inr.format(c.amount)}</dd></div>
              <div><dt className="text-muted">{t('bill.claimPaidOn')}</dt><dd>{date(c.paid_on)}</dd></div>
              <div><dt className="text-muted">{t('bill.claimRef')}</dt><dd className="font-mono">{c.reference}</dd></div>
              <div><dt className="text-muted">{t('bill.claimBalance')}</dt><dd className="tabular-nums">{inr.format(c.balance)}</dd></div>
            </dl>
            {c.note && <p className="text-muted">“{c.note}”</p>}
            {rejecting === c.id ? (
              <form onSubmit={(e) => { e.preventDefault(); void run(c.id, 'reject', { reason: why }) }} className="flex flex-wrap items-center gap-2">
                <input required minLength={3} maxLength={200} autoFocus value={why} onChange={(e) => setWhy(e.target.value)} placeholder={t('bill.rejectWhy')} aria-label={t('bill.rejectWhy')} className="h-10 min-w-64 flex-1 rounded-lg border border-line bg-surface px-3 outline-none focus:border-ink" />
                <button disabled={busy === c.id || why.trim().length < 3} className="h-10 rounded-lg bg-bad px-4 font-medium text-on-solid disabled:opacity-50">{t('bill.rejectGo')}</button>
                <button type="button" onClick={() => setRejecting(null)} className="h-10 px-3 text-muted hover:text-ink">{t('common.cancel')}</button>
              </form>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-2 text-muted">{t('bill.claimGot')}
                  <input inputMode="decimal" value={amounts[c.id] ?? String(c.amount)} onChange={(e) => setAmounts({ ...amounts, [c.id]: e.target.value.replace(/[^\d.]/g, '') })} className="h-10 w-32 rounded-lg border border-line bg-surface px-3 text-ink tabular-nums outline-none focus:border-ink" />
                </label>
                <button disabled={busy === c.id} onClick={() => void run(c.id, 'confirm', { amount: amounts[c.id] ?? String(c.amount) })} className="h-10 rounded-lg bg-ink px-4 font-medium text-surface hover:opacity-90 disabled:opacity-50">{t('bill.confirm')}</button>
                <button disabled={busy === c.id} onClick={() => { setRejecting(c.id); setWhy('') }} className="h-10 rounded-lg border border-line px-4 font-medium hover:border-ink">{t('bill.reject')}</button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
