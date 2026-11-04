import { CircleCheck, TriangleAlert } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { LineChart, StackedBars } from '../components/charts'
import { api, type Dashboard as Data } from '../lib/api'
import { useAuth } from '../lib/auth'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
/** Indian short form: 3.24 crore / 38.9 lakh / 12,000 */
const inrShort = (v: number) =>
  v >= 1e7 ? `₹${(v / 1e7).toFixed(2)} crore` : v >= 1e5 ? `₹${(v / 1e5).toFixed(1)} lakh` : inr.format(v)
const num = (v: number | null, d = 1, suffix = '') => (v === null ? '—' : `${v.toFixed(d)}${suffix}`)

function Tile({ title, value, target, ok, hint }: { title: string; value: string; target: string; ok: boolean | null; hint?: string }) {
  return (
    <div className="rounded-xl border border-line p-5">
      <div className="text-sm text-muted">{title}</div>
      <div className="mt-2 text-3xl font-semibold tabular-nums">{value}</div>
      <div className="mt-3 flex items-center gap-1.5 text-xs">
        {ok === null ? <span className="text-muted">No data yet</span> : ok
          ? <span className="inline-flex items-center gap-1 text-ok"><CircleCheck size={14} aria-hidden /> On target</span>
          : <span className="inline-flex items-center gap-1 text-warn"><TriangleAlert size={14} aria-hidden /> Below target</span>}
        <span className="text-muted">· target {target}</span>
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
  const [days, setDays] = useState(30)
  const [d, setD] = useState<Data | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    api<Data>(`/dashboard?days=${days}`).then(setD).catch(() => setError(true))
  }, [days])

  if (error) return <p className="text-bad">Could not load the dashboard.</p>
  if (!d) return <p className="text-muted">Loading…</p>

  const { kpis: k, targets: t, working_capital: w, missing: m, pipeline: p } = d
  const seg = (v: number) => `rounded-lg px-3 py-1.5 text-sm ${days === v ? 'bg-accent-soft font-medium text-accent' : 'text-muted hover:text-ink'}`

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{user?.role === 'md' ? 'Business overview' : 'Operations'}</h1>
          <p className="text-sm text-muted">Trips delivered in the last {d.window_days} days · {k.trips_in_window} trips</p>
        </div>
        <div className="flex gap-1" role="group" aria-label="Time window">
          {[30, 90].map((v) => <button key={v} className={seg(v)} onClick={() => setDays(v)} aria-pressed={days === v}>Last {v} days</button>)}
        </div>
      </div>

      {d.includes_demo_data && (
        <p className="rounded-lg bg-warn-soft px-4 py-2.5 text-sm text-warn" role="note">
          Showing illustrative DEMO data (trips coded DEMO-…). These figures are not real performance.
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Tile title="PODs in system within 24 h" value={num(k.within_24h_pct, 0, '%')} target={`${t.within_24h_pct}%`}
          ok={k.within_24h_pct === null ? null : k.within_24h_pct >= t.within_24h_pct} />
        <Tile title="POD to invoice" value={num(k.pod_to_invoice_days, 1, ' days')} target={`${t.pod_to_invoice_days} days`}
          ok={k.pod_to_invoice_days === null ? null : k.pod_to_invoice_days <= t.pod_to_invoice_days}
          hint={`Was ${t.baseline_pod_to_invoice_days} days before CargoOne`} />
        <Tile title="Lost or disputed PODs" value={num(k.lost_pct, 1, '%')} target={`${t.lost_pct}%`}
          ok={k.lost_pct === null ? null : k.lost_pct <= t.lost_pct} hint={`Was ${t.baseline_lost_pct}% before CargoOne`} />
        <div className="rounded-xl border border-line bg-accent-soft p-5">
          <div className="text-sm text-muted">Cash freed by faster billing</div>
          <div className="mt-2 text-3xl font-semibold tabular-nums">{w.released === null ? '—' : inrShort(w.released)}</div>
          <div className="mt-3 text-xs text-muted">
            {w.released === null ? 'Needs invoiced trips' : <>≈ {inrShort(w.interest_saved_per_year ?? 0)} interest saved a year at {Math.round(w.interest_rate * 100)}%</>}
          </div>
          <div className="mt-1 text-xs text-muted">
            {w.days_saved === null ? '' : `${w.days_saved.toFixed(1)} days sooner × ${inrShort(w.annual_freight)} yearly freight ÷ 365`}
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Link to="/office/review" className="rounded-xl border border-line px-5 py-4 hover:bg-wash">
          <div className="text-2xl font-semibold tabular-nums">{p.awaiting_review}</div><div className="text-sm text-muted">awaiting human review</div></Link>
        <Link to="/office/billing" className="rounded-xl border border-line px-5 py-4 hover:bg-wash">
          <div className="text-2xl font-semibold tabular-nums">{p.ready_to_bill} <span className="text-base font-normal text-muted">· {inr.format(p.ready_to_bill_amount)}</span></div><div className="text-sm text-muted">verified, ready to bill</div></Link>
        <div className="rounded-xl border border-line px-5 py-4">
          <div className="text-2xl font-semibold tabular-nums">{inr.format(m.at_risk_amount)}</div><div className="text-sm text-muted">freight at risk (POD missing 7+ days or rejected)</div></div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Trips without a POD" sub={`${m.total} trips · ${inr.format(m.amount)} freight · by days since delivery`}>
          {m.total === 0
            ? <p className="py-8 text-center text-sm text-muted">Every delivered trip has its POD.</p>
            : <StackedBars rows={m.by_branch.map((b) => ({ name: b.branch, buckets: b.buckets }))} />}
        </Panel>
        <Panel title="Branches" sub="Last window, per branch">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] text-left text-sm">
              <thead className="text-xs text-muted"><tr>
                <th className="pb-2 font-medium">Branch</th><th className="pb-2 font-medium">Within 24 h</th>
                <th className="pb-2 font-medium">To invoice</th><th className="pb-2 font-medium">Missing</th></tr></thead>
              <tbody>
                {d.branches.map((b) => (
                  <tr key={b.branch} className="border-t border-line">
                    <td className="py-2.5">{b.branch}</td>
                    <td className="py-2.5 tabular-nums">{num(b.within_24h_pct, 0, '%')}</td>
                    <td className="py-2.5 tabular-nums">{num(b.pod_to_invoice_days, 1, ' d')}</td>
                    <td className="py-2.5 tabular-nums">{b.missing}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="PODs within 24 h of delivery" sub="Share of delivered trips, by week">
          <LineChart points={d.trend.map((w) => ({ label: w.label, value: w.within_24h_pct }))}
            target={t.within_24h_pct} max={100} unit="PODs within 24 hours (%)" targetLabel={`Target ${t.within_24h_pct}%`} fmt={(v) => `${Math.round(v)}%`} />
        </Panel>
        <Panel title="Days from POD to invoice" sub="Average, by week the invoice was raised">
          <LineChart points={d.trend.map((w) => ({ label: w.label, value: w.pod_to_invoice_days }))}
            target={t.pod_to_invoice_days} max={20} unit="Days from POD to invoice" targetLabel={`Target ${t.pod_to_invoice_days} days`} fmt={(v) => `${v.toFixed(1)}`} />
        </Panel>
      </div>

      <Panel title="Oldest trips still without a POD" sub="Chase these first">
        {d.oldest_missing.length === 0 ? <p className="text-sm text-muted">None.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs text-muted"><tr>{['Trip', 'Client', 'Branch', 'Vehicle', 'Driver', 'Days', 'Freight'].map((h) => <th key={h} className="pb-2 font-medium">{h}</th>)}</tr></thead>
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
