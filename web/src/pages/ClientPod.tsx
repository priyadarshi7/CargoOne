import { CircleCheck, Clock, LinkIcon, LoaderCircle, RotateCw, ZoomIn, ZoomOut } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { BASE } from '../lib/api'

interface Pod {
  trip_code: string; lr_no: string; vehicle: string; origin: string; destination: string
  delivered_at: string | null; verified_at: string | null; expires_at: string; company: string
}
type State = { kind: 'loading' } | { kind: 'ok'; pod: Pod } | { kind: 'gone' } | { kind: 'unknown' } | { kind: 'error' }

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—')

/** Public, read-only page for a client: the signed proof of delivery for one trip. The link is the credential. */
export default function ClientPod() {
  const { token = '' } = useParams()
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [img, setImg] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [turns, setTurns] = useState(0)

  useEffect(() => {
    let url: string | null = null
    let alive = true
    const base = `${BASE}/v/${encodeURIComponent(token)}`
    fetch(base)
      .then(async (r) => {
        if (!alive) return
        if (!r.ok) return setState({ kind: r.status === 410 ? 'gone' : r.status === 404 ? 'unknown' : 'error' })
        setState({ kind: 'ok', pod: (await r.json()) as Pod })
        const im = await fetch(`${base}/image`)
        if (im.ok && alive) { url = URL.createObjectURL(await im.blob()); setImg(url) }
      })
      .catch(() => alive && setState({ kind: 'error' }))
    return () => { alive = false; if (url) URL.revokeObjectURL(url) }
  }, [token])

  if (state.kind === 'loading') return <Msg icon={<LoaderCircle size={40} className="animate-spin text-accent" aria-label="Loading" />} text="" />
  if (state.kind === 'gone') return <Msg icon={<Clock size={40} className="text-warn" />} text="This link has expired. Please ask the transporter for a new one." />
  if (state.kind === 'unknown') return <Msg icon={<LinkIcon size={40} className="text-bad" />} text="This link is not valid." />
  if (state.kind === 'error') return <Msg icon={<LinkIcon size={40} className="text-accent" />} text="The page could not be opened. Check your connection and try again." />

  const { pod } = state
  const btn = 'grid h-9 w-9 place-items-center rounded-lg border border-line bg-surface text-muted hover:text-ink'
  const facts: [string, string][] = [
    ['LR number', pod.lr_no], ['Vehicle', pod.vehicle], ['From', pod.origin], ['To', pod.destination], ['Delivered', day(pod.delivered_at)],
  ]
  return (
    <main className="mx-auto max-w-3xl space-y-8 px-4 py-10 sm:px-6">
      <header className="space-y-1">
        <p className="text-sm text-muted">{pod.company}</p>
        <h1 className="text-2xl font-semibold">Proof of delivery</h1>
        <p className="flex items-center gap-2 text-sm text-ok"><CircleCheck size={16} aria-hidden /> Verified {day(pod.verified_at)} · Trip {pod.trip_code}</p>
      </header>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
        {facts.map(([k, v]) => (<div key={k}><dt className="text-xs text-muted">{k}</dt><dd className="font-medium">{v}</dd></div>))}
      </dl>

      <section aria-label="Signed receipt" className="space-y-3">
        <div className="flex gap-2">
          <button className={btn} onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))} aria-label="Zoom out"><ZoomOut size={18} /></button>
          <button className={btn} onClick={() => setZoom((z) => Math.min(4, z + 0.25))} aria-label="Zoom in"><ZoomIn size={18} /></button>
          <button className={btn} onClick={() => setTurns((t) => t + 1)} aria-label="Rotate"><RotateCw size={18} /></button>
        </div>
        <div className="min-h-[50vh] overflow-auto rounded-xl border border-line bg-wash">
          {!img && <p className="p-6 text-sm text-muted">Loading the receipt…</p>}
          {img && <img src={img} alt="Signed delivery receipt" draggable={false} style={{ transform: `rotate(${turns * 90}deg)`, width: `${zoom * 100}%` }} className="mx-auto block max-w-none" />}
        </div>
      </section>
      <p className="text-xs text-muted">This link is read-only and expires on {day(pod.expires_at)}.</p>
    </main>
  )
}

function Msg({ icon, text }: { icon: React.ReactNode; text: string }) {
  return <main className="grid min-h-screen place-items-center px-6"><div className="flex max-w-sm flex-col items-center gap-4 text-center">{icon}<p>{text}</p></div></main>
}
