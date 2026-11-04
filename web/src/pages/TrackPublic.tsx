import { CircleCheck, Clock, LinkIcon, LoaderCircle, Truck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { LiveMap } from '../components/LiveMap'
import { BASE } from '../lib/api'

interface Track {
  trip_code: string; vehicle: string; origin: string; destination: string; state: 'planned' | 'in_transit' | 'delivered'
  lat: number | null; lng: number | null; seen_at: string | null; expires_at: string; company: string
}
type State = { kind: 'loading' } | { kind: 'ok'; t: Track } | { kind: 'gone' } | { kind: 'unknown' } | { kind: 'error' }

/** Public, read-only "where is my load?" page for a client. The link is the credential; the position is rounded to ~100 m. */
export default function TrackPublic() {
  const { token = '' } = useParams()
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    let alive = true
    const load = () => fetch(`${BASE}/t/${encodeURIComponent(token)}`)
      .then(async (r) => {
        if (!alive) return
        if (r.ok) return setState({ kind: 'ok', t: (await r.json()) as Track })
        setState({ kind: r.status === 410 ? 'gone' : r.status === 404 ? 'unknown' : 'error' })
      })
      .catch(() => alive && setState((s) => (s.kind === 'ok' ? s : { kind: 'error' })))
    void load()
    const id = setInterval(() => void load(), 30_000)
    return () => { alive = false; clearInterval(id) }
  }, [token])

  if (state.kind === 'loading') return <Msg icon={<LoaderCircle size={40} className="animate-spin text-accent" aria-label="Loading" />} text="" />
  if (state.kind === 'gone') return <Msg icon={<Clock size={40} className="text-warn" />} text="This link has expired. Please ask the transporter for a new one." />
  if (state.kind === 'unknown') return <Msg icon={<LinkIcon size={40} className="text-bad" />} text="This link is not valid." />
  if (state.kind === 'error') return <Msg icon={<LinkIcon size={40} className="text-accent" />} text="The page could not be opened. Check your connection and try again." />

  const { t } = state
  const mins = t.seen_at ? Math.max(0, Math.round((Date.now() - new Date(t.seen_at).getTime()) / 60_000)) : null
  return (
    <main className="mx-auto max-w-3xl space-y-6 px-4 py-10 sm:px-6">
      <header className="space-y-1">
        <p className="text-sm text-muted">{t.company}</p>
        <h1 className="text-2xl font-semibold">Where is my load?</h1>
        <p className="text-sm text-muted">Trip {t.trip_code} · {t.vehicle}</p>
      </header>

      <p className="flex items-center gap-2 text-lg font-medium">
        <span>{t.origin}</span><span className="text-muted">→</span><span>{t.destination}</span>
      </p>

      {t.state === 'delivered' ? (
        <p className="flex items-center gap-2 rounded-xl bg-ok-soft px-4 py-4 text-ok"><CircleCheck aria-hidden /> Delivered. Live tracking has ended.</p>
      ) : t.state === 'planned' ? (
        <p className="rounded-xl bg-wash px-4 py-4 text-muted">This trip has not left yet. The location will appear here once it is on the road.</p>
      ) : t.lat !== null && t.lng !== null ? (
        <>
          <p className="flex items-center gap-2 text-sm"><Truck size={16} className="text-accent" aria-hidden />
            On the road · last updated {mins === 0 ? 'just now' : `${mins} min ago`} · position is approximate</p>
          <div className="h-[24rem]"><LiveMap label="Map" points={[{ id: 'load', lat: t.lat, lng: t.lng, label: t.vehicle, tone: 'ok' }]} /></div>
        </>
      ) : (
        <p className="rounded-xl bg-wash px-4 py-4 text-muted">The truck is on the road, but its location is not available yet.</p>
      )}
      <p className="text-xs text-muted">This link is read-only and expires {new Date(t.expires_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}. Map data © OpenStreetMap contributors.</p>
    </main>
  )
}

function Msg({ icon, text }: { icon: React.ReactNode; text: string }) {
  return <main className="grid min-h-screen place-items-center px-6"><div className="flex max-w-sm flex-col items-center gap-4 text-center">{icon}<p>{text}</p></div></main>
}
