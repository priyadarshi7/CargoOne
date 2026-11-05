import { ArrowLeft, Check, RotateCcw, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { FIELD_LABEL, ImageViewer, type FoundBox } from '../components/ImageViewer'
import { ReasonChips } from '../components/ReasonChips'
import { api, ApiError, type ReviewItem } from '../lib/api'
import { useI18n } from '../lib/i18n'

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
  const { t } = useI18n()
  const nav = useNavigate()
  const [item, setItem] = useState<ReviewItem | null>(null)
  const [form, setForm] = useState<Form | null>(null)
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmReject, setConfirmReject] = useState(false)
  const [active, setActive] = useState<string | null>(null)

  useEffect(() => {
    api<ReviewItem>(`/review/${tripId}`).then((it) => { setItem(it); setForm(initial(it)) })
      .catch(() => setError(t('rd.loadFail')))
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
      setError(e instanceof ApiError ? e.message : t('rd.saveFail'))
      setConfirmReject(false)
    } finally {
      setBusy(false)
    }
  }, [item, form, note, busy, confirmReject, nav, t])

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

  if (!item || !form) return <p className={error ? 'text-bad' : 'text-muted'}>{error ?? t('common.loading')}</p>

  const field = 'h-11 w-full rounded-lg border border-line bg-surface px-3.5 text-sm outline-none focus:border-ink'
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm({ ...form, [k]: v })
  const boxes: FoundBox[] = Array.isArray(item.ai.boxes) ? (item.ai.boxes as FoundBox[]) : []
  const located = new Set(boxes.map((b) => b.field))
  // What the AI looked for; shown only when it drew boxes (the local reader). A missing one reads "not found".
  const seeking = boxes.length > 0 ? ['lr_no', 'delivery_date', 'quantity_received', 'remarks', 'stamp', 'signature'] : []
  const focus = (f: string) => ({ onFocus: () => setActive(f), onBlur: () => setActive(null), onMouseEnter: () => setActive(f), onMouseLeave: () => setActive(null) })
  const lrEmpty = norm(form.lr_no) === ''
  const lrChanged = !lrEmpty && norm(form.lr_no) !== norm(item.lr_no) // same rule as the server

  return (
    <div className="space-y-6">
      <Link to="/office/review" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft size={16} aria-hidden /> {t('review.title')}
      </Link>

      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <ImageViewer key={item.submission_id} submissionId={item.submission_id} boxes={boxes} active={active} onActive={setActive} />

        <div className="space-y-5 lg:sticky lg:top-20">
          <div className="rounded-2xl border border-line p-5">
            <h1 className="text-2xl font-semibold tracking-tight">{item.trip_code}</h1>
            <p className="text-sm text-muted">{item.client} · {item.destination} · LR {item.lr_no}</p>
            <div className="mt-3"><ReasonChips reasons={item.reasons} /></div>
            <p className="mt-3 text-xs text-muted">
              {t('rd.attempt', { n: item.attempt })}
              {item.confidence !== null && ` · ${t('rd.confidence', { n: Math.round(item.confidence * 100) })}`}
              {item.lat !== null && item.lng !== null && ` · GPS ${item.lat.toFixed(3)}, ${item.lng?.toFixed(3)}`}
            </p>
          </div>

          {seeking.length > 0 && (
            <div className="rounded-2xl border border-line p-5">
              <p className="text-xs font-medium uppercase tracking-wider text-muted">{t('rd.boxes')}</p>
              <ul className="mt-3 flex flex-wrap gap-2">
                {seeking.map((f) => {
                  const found = located.has(f)
                  const label = t(FIELD_LABEL[f] as 'rd.lr')
                  return (
                    <li key={f}>
                      <button type="button" disabled={!found} {...focus(f)} title={found ? t('rd.seen') : t('rd.notFound')}
                        className={`inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-sm ${found ? (active === f ? 'border-accent bg-accent-soft text-ink' : 'border-line text-ink hover:border-accent') : 'border-dashed border-line text-muted'}`}>
                        {found ? <Check size={14} aria-hidden /> : <X size={14} aria-hidden />} {label}
                      </button>
                    </li>
                  )
                })}
              </ul>
              <p className="mt-3 text-xs text-muted">{t('rd.boxHint')}</p>
            </div>
          )}

          <div className="space-y-4 rounded-2xl border border-line p-5">
            <p className="text-xs font-medium uppercase tracking-wider text-muted">{t('rd.check')}</p>
            <label className="block space-y-1 text-sm"><span className="font-medium">{t('rd.lr')}</span>
              <input {...focus('lr_no')} className={`${field} ${lrChanged ? 'border-warn' : ''}`} value={form.lr_no} onChange={(e) => set('lr_no', e.target.value)} />
              {lrEmpty && <span className="text-xs text-warn">{t('rd.lrUnread', { lr: item.lr_no })}</span>}
              {lrChanged && <span className="text-xs text-warn">{t('rd.lrDiff', { lr: item.lr_no })}</span>}
            </label>
            <label className="block space-y-1 text-sm"><span className="font-medium">{t('rd.date')}</span>
              <input type="date" {...focus('delivery_date')} className={field} value={form.delivery_date} onChange={(e) => set('delivery_date', e.target.value)} /></label>
            <label className="block space-y-1 text-sm"><span className="font-medium">{t('rd.qty')}</span>
              <input {...focus('quantity_received')} className={field} value={form.quantity_received} onChange={(e) => set('quantity_received', e.target.value)} /></label>
            <label className="block space-y-1 text-sm"><span className="font-medium">{t('rd.remarks')}</span>
              <input {...focus('remarks')} className={field} value={form.remarks} onChange={(e) => set('remarks', e.target.value)} /></label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="h-5 w-5 accent-[var(--color-ink)]" checked={form.shortage_or_damage} onChange={(e) => set('shortage_or_damage', e.target.checked)} />
              {t('rd.shortage')}
            </label>
            <label className="block space-y-1 text-sm"><span className="font-medium">{t('rd.note')}</span>
              <input className={field} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} /></label>
          </div>

          {error && <p role="alert" className="text-sm text-bad">{error}</p>}

          <div className="grid gap-2 sm:grid-cols-3">
            <button disabled={busy} onClick={() => void submit('approve')}
              className="flex h-12 items-center justify-center gap-2 rounded-xl bg-ok px-4 font-medium text-on-solid hover:opacity-90 disabled:opacity-60">
              <Check size={18} aria-hidden /> {t('rd.approve')} <kbd className="rounded border border-current px-1.5 text-[11px] font-sans opacity-70">A</kbd>
            </button>
            <button disabled={busy || item.retakes_left === 0} onClick={() => void submit('request_retake')}
              title={item.retakes_left === 0 ? t('rd.retakeLimit') : undefined}
              className="flex h-12 items-center justify-center gap-2 rounded-xl bg-warn px-4 font-medium text-on-solid hover:opacity-90 disabled:opacity-40">
              <RotateCcw size={18} aria-hidden /> {t('rd.retake')} <kbd className="rounded border border-current px-1.5 text-[11px] font-sans opacity-70">R</kbd>
            </button>
            <button disabled={busy} onClick={() => void submit('reject')}
              className={`flex h-12 items-center justify-center gap-2 rounded-xl px-4 font-medium disabled:opacity-60 ${confirmReject ? 'bg-bad text-on-solid' : 'border border-bad text-bad'}`}>
              <X size={18} aria-hidden /> {confirmReject ? t('rd.confirmReject') : t('rd.reject')} <kbd className="rounded border border-current px-1.5 text-[11px] font-sans opacity-70">X</kbd>
            </button>
          </div>
          <p className="text-xs text-muted">{t('rd.footer', { n: item.retakes_left })}</p>
        </div>
      </div>
    </div>
  )
}
