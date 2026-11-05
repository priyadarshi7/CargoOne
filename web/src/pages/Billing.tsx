import Attention from '../components/Attention'
import { FileCode2, FileText, Sheet } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, download, type Invoice, type QueueGroup } from '../lib/api'
import { useI18n } from '../lib/i18n'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const waiting = (iso: string | null) => (iso ? Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)) : 0)

export default function Billing() {
  const { t } = useI18n()
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
      setError(t('bill.error'))
    }
  }, [t])
  useEffect(() => { void load() }, [load])

  const tabBtn = (k: typeof tab, label: string, n?: number) => (
    <button onClick={() => setTab(k)} className={`border-b-2 px-1 pb-2 text-sm font-medium ${tab === k ? 'border-accent text-accent' : 'border-transparent text-muted hover:text-ink'}`}>
      {label}{n ? <span className="ml-1.5 text-xs text-muted">{n}</span> : null}
    </button>
  )

  if (error) return <p className="text-bad">{error}</p>
  if (!groups || !invoices) return <p className="text-muted">{t('common.loading')}</p>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t('bill.title')}</h1>
        <p className="text-sm text-muted">{t('bill.sub')}</p>
      </div>
      <Attention />
      <div className="flex gap-6 border-b border-line">
        {tabBtn('ready', t('bill.tabReady'), groups.reduce((n, g) => n + g.trips.length, 0))}
        {tabBtn('invoices', t('bill.tabInvoices'), invoices.length)}
      </div>
      {tab === 'ready'
        ? <Ready groups={groups} onCreated={async () => { await load(); setTab('invoices') }} onStale={load} />
        : <Invoices invoices={invoices} onExported={load} />}
    </div>
  )
}

function Ready({ groups, onCreated, onStale }: { groups: QueueGroup[]; onCreated: () => Promise<void>; onStale: () => Promise<void> }) {
  const { t } = useI18n()
  if (groups.length === 0) {
    return <div className="rounded-xl border border-line py-16 text-center text-muted">{t('bill.emptyReady')}</div>
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
    <section className="overflow-hidden rounded-xl border border-line">
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
              <td className="px-3 py-3 font-medium">{x.trip_code}<div className="text-xs font-normal text-muted">{x.lr_no} · EWB {x.eway_bill_no}</div></td>
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
          className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-surface disabled:opacity-50">
          {busy ? tx('bill.creating') : tx('bill.create')}
        </button>
      </footer>
    </section>
  )
}

function Invoices({ invoices, onExported }: { invoices: Invoice[]; onExported: () => Promise<void> }) {
  const { t, date } = useI18n()
  const [error, setError] = useState<string | null>(null)
  const get = async (inv: Invoice, kind: 'pdf' | 'tally' | 'csv') => {
    setError(null)
    try {
      await download(`/billing/invoices/${inv.id}/${kind}`, `${inv.invoice_no}.${kind === 'tally' ? 'xml' : kind}`)
      await onExported()
    } catch {
      setError(t('bill.dlFail'))
    }
  }
  if (invoices.length === 0) return <div className="rounded-xl border border-line py-16 text-center text-muted">{t('bill.emptyInvoices')}</div>
  const btn = 'inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-ink hover:border-accent hover:text-accent'
  return (
    <div className="space-y-3">
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="bg-wash text-muted">
            <tr>{(['bill.invoice', 'bill.client', 'bill.period', 'bill.tripsCol', 'bill.total', 'bill.exported', 'bill.download'] as const).map((h) => <th key={h} className="px-4 py-3 font-medium">{t(h)}</th>)}</tr>
          </thead>
          <tbody>
            {invoices.map((i) => (
              <tr key={i.id} className="border-t border-line">
                <td className="px-4 py-3 font-medium">{i.invoice_no}<div className="text-xs font-normal text-muted">{date(i.created_at)}</div></td>
                <td className="px-4 py-3">{i.client}</td>
                <td className="px-4 py-3 text-muted">{i.period_label ?? '—'}</td>
                <td className="px-4 py-3 tabular-nums">{i.trip_count}</td>
                <td className="px-4 py-3 tabular-nums">{inr.format(i.total)}</td>
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
    </div>
  )
}
