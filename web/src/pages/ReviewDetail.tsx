import { ArrowLeft, Check, RotateCcw, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ImageViewer } from '../components/ImageViewer'
import { ReasonChips } from '../components/ReasonChips'
import { api, ApiError, type ReviewItem } from '../lib/api'

type Form = { lr_no: string; delivery_date: string; quantity_received: string; remarks: string; shortage_or_damage: boolean }
type Action = 'approve' | 'request_retake' | 'reject'

/** Must match the server (api/app/routers/review.py `_norm`): ignore case, spaces and punctuation. */
const norm = (s: string) => s.toUpperCase().replace(/[^A-Z0-9]/g, '')
const str = (v: unknown) => (typeof v === 'string' ? v : '')
const initial = (it: ReviewItem): Form => {
  const v = { ...it.ai, ...(it.corrected ?? {}) }
  return {
    lr_no: str(v.lr_no), delivery_date: str(v.delivery_date), quantity_received: str(v.quantity_received),
    remarks: str(v.remarks), shortage_or_damage: v.shortage_or_damage === true,
  }
}

export default function ReviewDetail() {
  const { tripId = '' } = useParams()
  const nav = useNavigate()
  const [item, setItem] = useState<ReviewItem | null>(null)
  const [form, setForm] = useState<Form | null>(null)
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmReject, setConfirmReject] = useState(false)

  useEffect(() => {
    api<ReviewItem>(`/review/${tripId}`).then((it) => { setItem(it); setForm(initial(it)) })
      .catch(() => setError('Could not load this POD.'))
  }, [tripId])

  const submit = useCallback(async (action: Action) => {
    if (!item || !form || busy) return
    if (action === 'reject' && !confirmReject) return setConfirmReject(true)
    setBusy(true)
    setError(null)
    // Send only what the reviewer changed; the AI output is preserved server-side next to it.
    const base = initial({ ...item, corrected: null })
    const changed = Object.fromEntries(Object.entries(form).filter(([k, v]) => v !== base[k as keyof Form] && v !== ''))
    try {
      await api(`/review/${item.trip_id}/decision`, {
        method: 'POST',
        body: JSON.stringify({ action, corrected: action === 'approve' && Object.keys(changed).length ? changed : undefined, note: note || undefined }),
      })
      const rest = (await api<ReviewItem[]>('/review')).filter((i) => i.trip_id !== item.trip_id)
      nav(rest.length ? `/office/review/${rest[0].trip_id}` : '/office/review', { replace: true })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not save. Try again.')
      setConfirmReject(false)
    } finally {
      setBusy(false)
    }
  }, [item, form, note, busy, confirmReject, nav])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const t = e.target as HTMLElement
      if (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA') return
      if (e.key === 'a') void submit('approve')
      else if (e.key === 'r') void submit('request_retake')
      else if (e.key === 'x') void submit('reject')
      else if (e.key === 'Escape') setConfirmReject(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [submit])

  if (!item || !form) return <p className={error ? 'text-bad' : 'text-muted'}>{error ?? 'Loading…'}</p>

  const field = 'w-full rounded-lg border border-line px-3 py-2 text-sm outline-none focus:border-accent'
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm({ ...form, [k]: v })
  const lrEmpty = norm(form.lr_no) === ''
  const lrChanged = !lrEmpty && norm(form.lr_no) !== norm(item.lr_no) // same rule as the server

  return (
    <div className="space-y-6">
      <Link to="/office/review" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft size={16} aria-hidden /> Review queue
      </Link>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <ImageViewer key={item.submission_id} submissionId={item.submission_id} />

        <div className="space-y-6">
          <div>
            <h1 className="text-xl font-semibold">{item.trip_code}</h1>
            <p className="text-sm text-muted">{item.client} · {item.destination} · LR {item.lr_no}</p>
            <div className="mt-3"><ReasonChips reasons={item.reasons} /></div>
            <p className="mt-3 text-xs text-muted">
              Attempt {item.attempt}
              {item.confidence !== null && ` · AI confidence ${Math.round(item.confidence * 100)}%`}
              {item.lat !== null && item.lng !== null && ` · GPS ${item.lat.toFixed(3)}, ${item.lng?.toFixed(3)}`}
            </p>
          </div>

          <div className="space-y-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted">Check against the photo</p>
            <label className="block space-y-1 text-sm"><span className="text-muted">LR number</span>
              <input className={`${field} ${lrChanged ? 'border-warn' : ''}`} value={form.lr_no} onChange={(e) => set('lr_no', e.target.value)} />
              {lrEmpty && <span className="text-xs text-warn">LR number could not be read - type it from the photo (trip LR is {item.lr_no}).</span>}
              {lrChanged && <span className="text-xs text-warn">Differs from trip LR {item.lr_no} - approval will be refused.</span>}
            </label>
            <label className="block space-y-1 text-sm"><span className="text-muted">Delivery date</span>
              <input type="date" className={field} value={form.delivery_date} onChange={(e) => set('delivery_date', e.target.value)} /></label>
            <label className="block space-y-1 text-sm"><span className="text-muted">Quantity received</span>
              <input className={field} value={form.quantity_received} onChange={(e) => set('quantity_received', e.target.value)} /></label>
            <label className="block space-y-1 text-sm"><span className="text-muted">Remarks on the paper</span>
              <input className={field} value={form.remarks} onChange={(e) => set('remarks', e.target.value)} /></label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.shortage_or_damage} onChange={(e) => set('shortage_or_damage', e.target.checked)} />
              Shortage or damage recorded
            </label>
            <label className="block space-y-1 text-sm"><span className="text-muted">Note (optional)</span>
              <input className={field} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} /></label>
          </div>

          {error && <p role="alert" className="text-sm text-bad">{error}</p>}

          <div className="grid gap-2 sm:grid-cols-3">
            <button disabled={busy} onClick={() => void submit('approve')}
              className="flex items-center justify-center gap-2 rounded-lg bg-ok px-4 py-3 font-medium text-on-solid disabled:opacity-60">
              <Check size={18} aria-hidden /> Approve <kbd className="text-xs opacity-70">A</kbd>
            </button>
            <button disabled={busy || item.retakes_left === 0} onClick={() => void submit('request_retake')}
              title={item.retakes_left === 0 ? 'Retake limit reached' : undefined}
              className="flex items-center justify-center gap-2 rounded-lg bg-warn px-4 py-3 font-medium text-on-solid disabled:opacity-40">
              <RotateCcw size={18} aria-hidden /> Retake <kbd className="text-xs opacity-70">R</kbd>
            </button>
            <button disabled={busy} onClick={() => void submit('reject')}
              className={`flex items-center justify-center gap-2 rounded-lg px-4 py-3 font-medium disabled:opacity-60 ${confirmReject ? 'bg-bad text-on-solid' : 'border border-bad text-bad'}`}>
              <X size={18} aria-hidden /> {confirmReject ? 'Confirm reject' : 'Reject'} <kbd className="text-xs opacity-70">X</kbd>
            </button>
          </div>
          <p className="text-xs text-muted">Approving does not send an invoice. Retakes left for the driver: {item.retakes_left}.</p>
        </div>
      </div>
    </div>
  )
}
