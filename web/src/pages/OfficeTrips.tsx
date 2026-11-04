import { useEffect, useState } from 'react'
import { StatusBadge } from '../components/StatusBadge'
import { api, type Trip } from '../lib/api'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const day = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }) : '—'

export default function OfficeTrips() {
  const [trips, setTrips] = useState<Trip[] | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    api<Trip[]>('/trips').then(setTrips).catch(() => setError(true))
  }, [])

  if (error) return <p className="text-bad">Could not load trips.</p>
  if (!trips) return <p className="text-muted">Loading…</p>

  const count = (s: Trip['pod_status']) => trips.filter((t) => t.pod_status === s).length
  const stats = [
    ['Trips', trips.length],
    ['Verified', count('verified')],
    ['Needs review', count('needs_review')],
    ['Retake', count('retake_requested')],
  ] as const

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {stats.map(([label, n]) => (
          <div key={label} className="rounded-xl border border-line p-4">
            <div className="text-2xl font-semibold tabular-nums">{n}</div>
            <div className="text-sm text-muted">{label}</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="bg-wash text-muted">
            <tr>
              {['Trip', 'Client', 'Vehicle', 'To', 'Freight', 'Delivered', 'POD'].map((h) => (
                <th key={h} className="px-4 py-3 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {trips.map((t) => (
              <tr key={t.id} className="border-t border-line">
                <td className="px-4 py-3 font-medium">{t.trip_code}<div className="text-xs font-normal text-muted">{t.lr_no}</div></td>
                <td className="px-4 py-3">{t.client}</td>
                <td className="px-4 py-3">{t.vehicle}{t.is_hired && <span className="ml-1.5 text-xs text-muted">hired</span>}</td>
                <td className="px-4 py-3">{t.destination}</td>
                <td className="px-4 py-3 tabular-nums">{inr.format(t.freight_amount)}</td>
                <td className="px-4 py-3">{day(t.delivered_at)}</td>
                <td className="px-4 py-3"><StatusBadge status={t.pod_status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
