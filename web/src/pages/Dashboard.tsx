import { CircleCheck, FileDown, TriangleAlert } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import Attention from '../components/Attention'
import { LineChart, StackedBars } from '../components/charts'
import { api, download, type Dashboard as Data } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
/** Indian short form: 3.24 crore / 38.9 lakh / 12,000 */
const inrShort = (v: number, u: { crore: string; lakh: string }) =>
  v >= 1e7 ? `₹${(v / 1e7).toFixed(2)} ${u.crore}` : v >= 1e5 ? `₹${(v / 1e5).toFixed(1)} ${u.lakh}` : inr.format(v)
const num = (v: number | null, d = 1, suffix = '') => (v === null ? '—' : `${v.toFixed(d)}${suffix}`)

function Tile({ title, value, target, ok, hint }: { title: string; value: string; target: string; ok: boolean | null; hint?: string }) {
  const { t } = useI18n()
  return (
    <div className="rounded-xl border border-line p-5">
      <div className="text-sm text-muted">{title}</div>
      <div className="mt-2 text-3xl font-semibold tabular-nums">{value}</div>
      <div className="mt-3 flex items-center gap-1.5 text-xs">
        {ok === null ? <span className="text-muted">{t('dash.noData')}</span> : ok
          ? <span className="inline-flex items-center gap-1 text-ok"><CircleCheck size={14} aria-hidden /> {t('dash.onTarget')}</span>
          : <span className="inline-flex items-center gap-1 text-warn"><TriangleAlert size={14} aria-hidden /> {t('dash.below')}</span>}
        <span className="text-muted">· {t('dash.target', { v: target })}</span>
      </div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  )
}

function Panel({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-line p-5">
      <h2 className="font-semibold">{title}</h2>
      {sub && <p className="mb-4 text-xs text-muted">{sub}</p>}
      <div className={sub ? '' : 'mt-4'}>{children}</div>
    </section>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const { t: tr } = useI18n()
  const u = { crore: tr('unit.crore'), lakh: tr('unit.lakh') }
  const [days, setDays] = useState(30)
  const [d, setD] = useState<Data | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    api<Data>(`/dashboard?days=${days}`).then(setD).catch(() => setError(true))
  }, [days])

  if (error) return <p className="text-bad">{tr('dash.error')}</p>
  if (!d) return <p className="text-muted">{tr('common.loading')}</p>

  const { kpis: k, targets: t, working_capital: w, missing: m, pipeline: p } = d
  const seg = (v: number) => `rounded-lg px-3 py-1.5 text-sm ${days === v ? 'bg-accent-soft font-medium text-accent' : 'text-muted hover:text-ink'}`

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{user?.role === 'md' ? tr('dash.md') : tr('dash.ops')}</h1>
          <p className="text-sm text-muted">{tr('dash.sub', { days: d.window_days, n: k.trips_in_window })}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex gap-1" role="group" aria-label={tr('dash.window')}>
            {[30, 90].map((v) => <button key={v} className={seg(v)} onClick={() => setDays(v)} aria-pressed={days === v}>{tr('dash.last', { n: v })}</button>)}
          </div>
          <button onClick={() => void download(`/dashboard/digest.pdf?days=${days}`, 'cargoone-digest.pdf')}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm hover:border-accent hover:text-accent">
            <FileDown size={16} aria-hidden /> {tr('dash.digest')}
          </button>
        </div>
      </div>

      <Attention />

      {d.includes_demo_data && (
        <p className="rounded-lg bg-warn-soft px-4 py-2.5 text-sm text-warn" role="note">
          {tr('dash.demo')}
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Tile title={tr('dash.pod24')} value={num(k.within_24h_pct, 0, '%')} target={`${t.within_24h_pct}%`}
          ok={k.within_24h_pct === null ? null : k.within_24h_pct >= t.within_24h_pct} />
        <Tile title={tr('dash.invoice')} value={num(k.pod_to_invoice_days, 1, tr('unit.days'))} target={`${t.pod_to_invoice_days}${tr('unit.days')}`}
          ok={k.pod_to_invoice_days === null ? null : k.pod_to_invoice_days <= t.pod_to_invoice_days}
          hint={tr('dash.was', { v: `${t.baseline_pod_to_invoice_days}${tr('unit.days')}` })} />
        <Tile title={tr('dash.lost')} value={num(k.lost_pct, 1, '%')} target={`${t.lost_pct}%`}
          ok={k.lost_pct === null ? null : k.lost_pct <= t.lost_pct} hint={tr('dash.was', { v: `${t.baseline_lost_pct}%` })} />
        <div className="rounded-xl border border-line bg-accent-soft p-5">
          <div className="text-sm text-muted">{tr('dash.cash')}</div>
          <div className="mt-2 text-3xl font-semibold tabular-nums">{w.released === null ? '—' : inrShort(w.released, u)}</div>
          <div className="mt-3 text-xs text-muted">
            {w.released === null ? tr('dash.needsInvoiced') : tr('dash.interest', { amt: inrShort(w.interest_saved_per_year ?? 0, u), pct: Math.round(w.interest_rate * 100) })}
          </div>
          <div className="mt-1 text-xs text-muted">
            {w.days_saved === null ? '' : tr('dash.calc', { d: w.days_saved.toFixed(1), amt: inrShort(w.annual_freight, u) })}
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Link to="/office/review" className="rounded-xl border border-line px-5 py-4 hover:bg-wash">
          <div className="text-2xl font-semibold tabular-nums">{p.awaiting_review}</div><div className="text-sm text-muted">{tr('dash.awaiting')}</div></Link>
        <Link to="/office/billing" className="rounded-xl border border-line px-5 py-4 hover:bg-wash">
          <div className="text-2xl font-semibold tabular-nums">{p.ready_to_bill} <span className="text-base font-normal text-muted">· {inr.format(p.ready_to_bill_amount)}</span></div><div className="text-sm text-muted">{tr('dash.ready')}</div></Link>
        <div className="rounded-xl border border-line px-5 py-4">
          <div className="text-2xl font-semibold tabular-nums">{inr.format(m.at_risk_amount)}</div><div className="text-sm text-muted">{tr('dash.risk')}</div></div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title={tr('dash.missing')} sub={tr('dash.missingSub', { n: m.total, amt: inr.format(m.amount) })}>
          {m.total === 0
            ? <p className="py-8 text-center text-sm text-muted">{tr('dash.allHave')}</p>
            : <StackedBars rows={m.by_branch.map((b) => ({ name: b.branch, buckets: b.buckets }))} />}
        </Panel>
        <Panel title={tr('dash.branches')} sub={tr('dash.branchesSub')}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] text-left text-sm">
              <thead className="text-xs text-muted"><tr>
                <th className="pb-2 font-medium">{tr('dash.branch')}</th><th className="pb-2 font-medium">{tr('dash.within24')}</th>
                <th className="pb-2 font-medium">{tr('dash.toInvoice')}</th><th className="pb-2 font-medium">{tr('dash.missingCol')}</th></tr></thead>
              <tbody>
                {d.branches.map((b) => (
                  <tr key={b.branch} className="border-t border-line">
                    <td className="py-2.5">{b.branch}</td>
                    <td className="py-2.5 tabular-nums">{num(b.within_24h_pct, 0, '%')}</td>
                    <td className="py-2.5 tabular-nums">{num(b.pod_to_invoice_days, 1, tr('unit.d'))}</td>
                    <td className="py-2.5 tabular-nums">{b.missing}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title={tr('dash.c1')} sub={tr('dash.c1sub')}>
          <LineChart points={d.trend.map((w) => ({ label: w.label, value: w.within_24h_pct }))}
            target={t.within_24h_pct} max={100} unit={tr('dash.c1unit')} targetLabel={tr('dash.c1target', { v: t.within_24h_pct })} fmt={(v) => `${Math.round(v)}%`} />
        </Panel>
        <Panel title={tr('dash.c2')} sub={tr('dash.c2sub')}>
          <LineChart points={d.trend.map((w) => ({ label: w.label, value: w.pod_to_invoice_days }))}
            target={t.pod_to_invoice_days} max={20} unit={tr('dash.c2unit')} targetLabel={tr('dash.c2target', { v: t.pod_to_invoice_days })} fmt={(v) => `${v.toFixed(1)}`} />
        </Panel>
      </div>

      <Panel title={tr('dash.oldest')} sub={tr('dash.oldestSub')}>
        {d.oldest_missing.length === 0 ? <p className="text-sm text-muted">{tr('common.none')}</p> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs text-muted"><tr>{(['dash.cTrip', 'dash.cClient', 'dash.branch', 'dash.cVehicle', 'dash.cDriver', 'dash.cDays', 'dash.cFreight'] as const).map((h) => <th key={h} className="pb-2 font-medium">{tr(h)}</th>)}</tr></thead>
              <tbody>
                {d.oldest_missing.map((r) => (
                  <tr key={r.trip_code} className="border-t border-line">
                    <td className="py-2.5 font-medium">{r.trip_code}</td><td className="py-2.5">{r.client}</td>
                    <td className="py-2.5 text-muted">{r.branch}</td><td className="py-2.5 text-muted">{r.vehicle}</td>
                    <td className="py-2.5 text-muted">{r.driver ?? '—'}</td>
                    <td className="py-2.5 tabular-nums">{r.age_days}</td><td className="py-2.5 tabular-nums">{inr.format(r.freight)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}
