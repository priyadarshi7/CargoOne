import { FileCode2, FileText, Sheet } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, download, type Invoice, type QueueGroup } from '../lib/api'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const date = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
const waiting = (iso: string | null) => (iso ? Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)) : 0)

export default function Billing() {
  const [tab, setTab] = useState<'ready' | 'invoices'>('ready')
  const [groups, setGroups] = useState<QueueGroup[] | null>(null)
  const [invoices, setInvoices] = useState<Invoice[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [g, i] = await Promise.all([api<QueueGroup[]>('/billing/queue'), api<Invoice[]>('/billing/invoices')])
      setGroups(g)
      setInvoices(i)
    } catch {
      setError('Could not load billing data.')
    }
  }, [])
  useEffect(() => { void load() }, [load])

  const tabBtn = (t: typeof tab, label: string, n?: number) => (
    <button onClick={() => setTab(t)} className={`border-b-2 px-1 pb-2 text-sm font-medium ${tab === t ? 'border-accent text-accent' : 'border-transparent text-muted hover:text-ink'}`}>
      {label}{n ? <span className="ml-1.5 text-xs text-muted">{n}</span> : null}
    </button>
  )

  if (error) return <p className="text-bad">{error}</p>
  if (!groups || !invoices) return <p className="text-muted">Loading…</p>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Billing</h1>
        <p className="text-sm text-muted">Verified PODs, ready to invoice. Nothing is sent to a client automatically.</p>
      </div>
      <div className="flex gap-6 border-b border-line">
        {tabBtn('ready', 'Ready to bill', groups.reduce((n, g) => n + g.trips.length, 0))}
        {tabBtn('invoices', 'Invoices', invoices.length)}
      </div>
      {tab === 'ready'
        ? <Ready groups={groups} onCreated={async () => { await load(); setTab('invoices') }} onStale={load} />
        : <Invoices invoices={invoices} onExported={load} />}
    </div>
  )
}

function Ready({ groups, onCreated, onStale }: { groups: QueueGroup[]; onCreated: () => Promise<void>; onStale: () => Promise<void> }) {
  if (groups.length === 0) {
    return <div className="rounded-xl border border-line py-16 text-center text-muted">No verified PODs waiting to be billed.</div>
  }
  return <div className="space-y-6">{groups.map((g) => <Group key={`${g.client_id}-${g.period_key}`} group={g} onCreated={onCreated} onStale={onStale} />)}</div>
}

function Group({ group, onCreated, onStale }: { group: QueueGroup; onCreated: () => Promise<void>; onStale: () => Promise<void> }) {
  const [picked, setPicked] = useState<Set<string>>(() => new Set(group.trips.map((t) => t.id)))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const chosen = group.trips.filter((t) => picked.has(t.id))
  const sum = chosen.reduce((n, t) => n + t.freight_amount, 0)

  const toggle = (id: string) => setPicked((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n })

  async function create() {
    setBusy(true)
    setError(null)
    try {
      await api('/billing/invoices', { method: 'POST', body: JSON.stringify({ trip_ids: chosen.map((t) => t.id) }) })
      await onCreated()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not create the invoice.')
      if (e instanceof ApiError && e.status === 409) await onStale() // someone else billed these - refresh
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="overflow-hidden rounded-xl border border-line">
      <header className="flex flex-wrap items-baseline justify-between gap-2 bg-wash px-5 py-3">
        <div>
          <span className="font-semibold">{group.client}</span>
          <span className="ml-3 text-sm text-muted">{group.period_label} · {group.billing_cycle}</span>
        </div>
        <span className="text-sm text-muted">oldest waiting {waiting(group.oldest_verified_at)} days</span>
      </header>
      <table className="w-full text-left text-sm">
        <tbody>
          {group.trips.map((t) => (
            <tr key={t.id} className="border-t border-line">
              <td className="w-10 py-3 pl-5"><input type="checkbox" checked={picked.has(t.id)} onChange={() => toggle(t.id)} aria-label={`Include ${t.trip_code}`} /></td>
              <td className="px-3 py-3 font-medium">{t.trip_code}<div className="text-xs font-normal text-muted">{t.lr_no} · EWB {t.eway_bill_no}</div></td>
              <td className="px-3 py-3">{t.destination}</td>
              <td className="px-3 py-3 text-muted">{t.delivered_at ? date(t.delivered_at) : '—'}</td>
              <td className="py-3 pr-5 text-right tabular-nums">{inr.format(t.freight_amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-5 py-3">
        <div className="text-sm"><span className="text-muted">{chosen.length} of {group.trips.length} {group.trips.length === 1 ? 'trip' : 'trips'} · </span><span className="font-semibold tabular-nums">{inr.format(sum)}</span></div>
        {error && <span role="alert" className="text-sm text-bad">{error}</span>}
        <button disabled={busy || chosen.length === 0} onClick={() => void create()}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-on-solid disabled:opacity-50">
          {busy ? 'Creating…' : 'Create invoice'}
        </button>
      </footer>
    </section>
  )
}

function Invoices({ invoices, onExported }: { invoices: Invoice[]; onExported: () => Promise<void> }) {
  const [error, setError] = useState<string | null>(null)
  const get = async (inv: Invoice, kind: 'pdf' | 'tally' | 'csv') => {
    setError(null)
    try {
      await download(`/billing/invoices/${inv.id}/${kind}`, `${inv.invoice_no}.${kind === 'tally' ? 'xml' : kind}`)
      await onExported()
    } catch {
      setError('Download failed. Try again.')
    }
  }
  if (invoices.length === 0) return <div className="rounded-xl border border-line py-16 text-center text-muted">No invoices yet.</div>
  const btn = 'inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-ink hover:border-accent hover:text-accent'
  return (
    <div className="space-y-3">
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="bg-wash text-muted">
            <tr>{['Invoice', 'Client', 'Period', 'Trips', 'Total', 'Exported', 'Download'].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {invoices.map((i) => (
              <tr key={i.id} className="border-t border-line">
                <td className="px-4 py-3 font-medium">{i.invoice_no}<div className="text-xs font-normal text-muted">{date(i.created_at)}</div></td>
                <td className="px-4 py-3">{i.client}</td>
                <td className="px-4 py-3 text-muted">{i.period_label ?? '—'}</td>
                <td className="px-4 py-3 tabular-nums">{i.trip_count}</td>
                <td className="px-4 py-3 tabular-nums">{inr.format(i.total)}</td>
                <td className="px-4 py-3">{i.exported_at ? <span className="text-ok">{date(i.exported_at)}</span> : <span className="text-muted">Not yet</span>}</td>
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
      <p className="text-xs text-muted">The PDF includes each trip's POD photo. Tally XML imports as a Sales voucher; the party and freight ledgers must already exist in Tally.</p>
    </div>
  )
}
