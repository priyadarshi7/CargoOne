import { Camera, CircleCheck, CloudUpload, LogOut } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { statusIcon } from '../components/StatusBadge'
import { api, type PodStatus, type Trip } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useSyncedQueue } from '../lib/capture/sync'

const OPEN: PodStatus[] = ['pending', 'retake_requested']

/** Driver surface: one primary action, icons over text, no forms. */
export default function DriverHome() {
  const { user, logout } = useAuth()
  const pending = useSyncedQueue()
  const [trips, setTrips] = useState<Trip[] | null>(null)

  useEffect(() => {
    api<Trip[]>('/trips/mine').then(setTrips).catch(() => setTrips([]))
  }, [pending]) // refresh statuses after queued photos finish uploading

  const next = trips?.find((t) => OPEN.includes(t.pod_status))

  return (
    <div className="mx-auto flex min-h-full max-w-md flex-col px-5 pb-8 pt-6">
      <header className="flex items-center justify-between">
        <p className="text-lg font-medium">{user?.name}</p>
        <button onClick={logout} aria-label="Sign out" className="grid h-12 w-12 place-items-center rounded-full text-muted">
          <LogOut aria-hidden />
        </button>
      </header>

      {pending > 0 && (
        <div className="mt-4 flex items-center gap-3 rounded-2xl bg-accent-soft p-4 text-accent" role="status">
          <CloudUpload aria-hidden /> <span className="text-lg font-semibold tabular-nums">{pending}</span>
        </div>
      )}

      {next ? (
        <Link to={`/driver/trip/${next.id}`}
          className="mt-6 grid h-48 w-full place-items-center rounded-3xl bg-accent text-white active:scale-[0.98]">
          <span className="flex flex-col items-center gap-3 text-xl font-semibold">
            <Camera size={64} aria-hidden /> POD
            <span className="text-base font-normal opacity-90">{next.destination}</span>
          </span>
        </Link>
      ) : (
        trips && (
          <div className="mt-6 grid h-48 w-full place-items-center rounded-3xl bg-ok-soft text-ok">
            <CircleCheck size={80} aria-label="All done" />
          </div>
        )
      )}

      <ul className="mt-8 space-y-3">
        {trips?.map((t) => {
          const { icon: Icon, cls, label } = statusIcon(t.pod_status)
          return (
            <li key={t.id} className="flex items-center gap-4 rounded-2xl border border-line p-4">
              <span className={`grid h-14 w-14 shrink-0 place-items-center rounded-full ${cls}`} title={label}>
                <Icon size={28} aria-label={label} />
              </span>
              <div className="min-w-0">
                <div className="truncate text-lg font-semibold">{t.destination}</div>
                <div className="truncate text-sm text-muted">{t.trip_code} · {t.vehicle}</div>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
