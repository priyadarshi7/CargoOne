import { useEffect, useState } from 'react'
import { StatusBadge } from '../components/StatusBadge'
import { Link } from 'react-router-dom'
import { ClientLinkDialog } from '../components/ClientLinkDialog'
import { ShipmentDialog } from '../components/ShipmentDialog'
import { UploadLinkDialog } from '../components/UploadLinkDialog'
import { api, download, type Trip } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const day = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }) : '—'

/** Trips whose latest state means a photo was taken: the read-only POD view (what the AI read, with boxes) has something to show. */
const HAS_PHOTO = new Set(['uploaded', 'needs_review', 'verified', 'billed', 'rejected', 'retake_requested'])

export default function OfficeTrips() {
  const { user } = useAuth()
  const { t: tx } = useI18n()
  const canSendLink = user?.role === 'ops' || user?.role === 'billing' || user?.role === 'admin'
  const [linkFor, setLinkFor] = useState<Trip | null>(null)
  const [shareFor, setShareFor] = useState<Trip | null>(null)
  const [journeyFor, setJourneyFor] = useState<Trip | null>(null)
  const [trips, setTrips] = useState<Trip[] | null>(null)
  const [error, setError] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  useEffect(() => {
    api<Trip[]>('/trips').then(setTrips).catch(() => setError(true))
  }, [])

  if (error) return <p className="text-bad">{tx('trips.error')}</p>
  if (!trips) return <p className="text-muted">{tx('common.loading')}</p>

  const count = (s: Trip['pod_status']) => trips.filter((t) => t.pod_status === s).length
  const stats = [
    [tx('trips.total'), trips.length],
    [tx('trips.verified'), count('verified')],
    [tx('trips.needsReview'), count('needs_review')],
    [tx('trips.retake'), count('retake_requested')],
  ] as const

  return (
    <div className="space-y-8">
      <h1 className="text-3xl font-semibold tracking-tight">{tx('nav.trips')}</h1>
      {note && <p role="alert" className="text-sm text-bad">{note}</p>}
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
              {(['trips.trip', 'trips.client', 'trips.vehicle', 'trips.to', 'trips.freight', 'trips.delivered', 'trips.pod', ...(canSendLink ? ['trips.uploadLink' as const] : [])] as const).map((h) => (
                <th key={h} className="px-4 py-3 font-medium">{tx(h)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {trips.map((t) => (
              <tr key={t.id} className="border-t border-line">
                <td className="px-4 py-3 font-medium"><button onClick={() => setJourneyFor(t)} className="underline-offset-2 hover:text-accent hover:underline" aria-label={`${tx('sh.open')} ${t.trip_code}`}>{t.trip_code}</button><div className="text-xs font-normal text-muted">{t.lr_no}{canSendLink && <button onClick={() => void download(`/trips/${t.id}/lr.pdf`, `${t.trip_code}-LR.pdf`).catch(() => setNote(tx('lr.pdfFail')))} className="ml-2 underline hover:text-accent">{tx('lr.pdf')}</button>}</div></td>
                <td className="px-4 py-3">{t.client}</td>
                <td className="px-4 py-3">{t.vehicle}{t.is_hired && <span className="ml-1.5 text-xs text-muted">{tx('trips.hired')}</span>}</td>
                <td className="px-4 py-3">{t.destination}</td>
                <td className="px-4 py-3 tabular-nums">{inr.format(t.freight_amount)}</td>
                <td className="px-4 py-3">{day(t.delivered_at)}</td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center gap-2"><StatusBadge status={t.pod_status} />
                    {HAS_PHOTO.has(t.pod_status) && <Link to={`/office/review/${t.id}`} className="text-xs font-medium underline hover:text-accent">{tx('trips.viewPod')}</Link>}
                  </span>
                </td>
                {canSendLink && (
                  <td className="px-4 py-3">
                    {(t.pod_status === 'pending' || t.pod_status === 'retake_requested') && (
                      <button onClick={() => setLinkFor(t)} className="rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium hover:border-accent hover:text-accent">
                        {t.is_hired ? tx('trips.sendLink') : tx('trips.link')}
                      </button>
                    )}
                    {(t.pod_status === 'verified' || t.pod_status === 'billed') && (
                      <button onClick={() => setShareFor(t)} className="rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium hover:border-accent hover:text-accent">
                        {tx('trips.share')}
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {linkFor && <UploadLinkDialog trip={linkFor} onClose={() => setLinkFor(null)} />}
      {journeyFor && <ShipmentDialog trip={journeyFor} canAct={user?.role === 'ops' || user?.role === 'admin'} onClose={() => setJourneyFor(null)} />}
      {shareFor && <ClientLinkDialog trip={shareFor} onClose={() => setShareFor(null)} />}
    </div>
  )
}
