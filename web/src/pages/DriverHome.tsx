import { Camera, LogOut } from 'lucide-react'
import { useEffect, useState } from 'react'
import { statusIcon } from '../components/StatusBadge'
import { api, type Trip } from '../lib/api'
import { useAuth } from '../lib/auth'

/** Driver surface: one primary action, icons over text, no forms. Camera capture ships in the next PR. */
export default function DriverHome() {
  const { user, logout } = useAuth()
  const [trips, setTrips] = useState<Trip[] | null>(null)

  useEffect(() => {
    api<Trip[]>('/trips/mine').then(setTrips).catch(() => setTrips([]))
  }, [])

  return (
    <div className="mx-auto flex min-h-full max-w-md flex-col px-5 pb-8 pt-6">
      <header className="flex items-center justify-between">
        <p className="text-lg font-medium">{user?.name}</p>
        <button onClick={logout} aria-label="Sign out" className="grid h-12 w-12 place-items-center rounded-full text-muted">
          <LogOut aria-hidden />
        </button>
      </header>

      <button disabled aria-describedby="soon"
        className="mt-8 grid h-48 w-full place-items-center rounded-3xl bg-accent text-white disabled:opacity-90">
        <span className="flex flex-col items-center gap-3 text-xl font-semibold">
          <Camera size={64} aria-hidden /> POD
        </span>
      </button>
      <p id="soon" className="mt-2 text-center text-xs text-muted">Camera capture is being built.</p>

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
