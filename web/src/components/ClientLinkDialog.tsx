import { Check, Copy, Share2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, ApiError, type Trip } from '../lib/api'

interface LinkOut { url: string; expires_at: string }
interface Row { created_at: string; expires_at: string; revoked: boolean; views: number; last_viewed_at: string | null }
const when = (iso: string) => new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })

/** Office action: a read-only link so the client can see the verified POD for this trip, plus who opened it. */
export function ClientLinkDialog({ trip, onClose }: { trip: Trip; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const [link, setLink] = useState<LinkOut | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [now] = useState(() => Date.now())

  const load = () => api<Row[]>(`/trips/${trip.id}/view-links`).then(setRows).catch(() => undefined)
  useEffect(() => { ref.current?.showModal(); void load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function create() {
    setBusy(true)
    setError(null)
    try {
      setLink(await api<LinkOut>(`/trips/${trip.id}/view-link`, { method: 'POST' }))
      void load()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not create the link.')
    } finally {
      setBusy(false)
    }
  }

  async function revoke() {
    await api(`/trips/${trip.id}/view-link`, { method: 'DELETE' }).catch(() => undefined)
    setLink(null)
    void load()
  }

  async function copy() {
    if (!link) return
    await navigator.clipboard?.writeText(link.url).catch(() => undefined)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const active = rows.some((r) => !r.revoked && new Date(r.expires_at).getTime() > now)
  return (
    <dialog ref={ref} onClose={onClose} aria-label="Share with client"
      className="m-auto w-[min(32rem,92vw)] rounded-2xl border border-line p-0 shadow-xl backdrop:bg-black/30">
      <div className="space-y-5 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold"><Share2 size={18} aria-hidden /> Share with client</h2>
            <p className="text-sm text-muted">{trip.trip_code} · {trip.client} · {trip.destination}</p>
          </div>
          <button onClick={() => ref.current?.close()} aria-label="Close" className="text-muted hover:text-ink"><X size={20} /></button>
        </div>

        <p className="text-sm text-muted">The client opens the link and sees the signed receipt photo, LR number and delivery date. Nothing else: no amounts, no other trips, no way to change anything.</p>

        {link ? (
          <div className="flex gap-2">
            <input readOnly aria-label="Client link" value={link.url} className="w-full rounded-lg border border-line px-3 py-2 font-mono text-xs outline-none" onFocus={(e) => e.currentTarget.select()} />
            <button onClick={() => void copy()} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 text-sm hover:border-accent">
              {copied ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />} {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
        ) : (
          <button disabled={busy} onClick={() => void create()} className="w-full rounded-lg bg-accent py-2.5 font-medium text-white disabled:opacity-60">
            {busy ? 'Creating…' : active ? 'Create a new link (cancels the old one)' : 'Create link'}
          </button>
        )}
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}

        {rows.length > 0 && (
          <div>
            <h3 className="mb-1 text-sm font-medium">Access log</h3>
            <ul className="divide-y divide-line rounded-xl border border-line text-sm">
              {rows.map((r) => (
                <li key={r.created_at} className="space-y-0.5 px-3 py-2">
                  <div>Created {when(r.created_at)}</div>
                  <div className="text-muted">
                    {r.revoked ? 'revoked' : new Date(r.expires_at).getTime() < now ? 'expired' : `until ${when(r.expires_at)}`}
                    {' · '}{r.views === 0 ? 'not opened yet' : `opened ${r.views}× (last ${when(r.last_viewed_at!)})`}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
        {active && <button onClick={() => void revoke()} className="text-sm text-bad underline underline-offset-2">Revoke access</button>}
      </div>
    </dialog>
  )
}
