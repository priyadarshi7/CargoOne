import { X } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { ApiError } from '../lib/api'
import { translate, type Key, type Lang } from '../lib/i18n'

const big = 'h-16 w-full rounded-2xl text-xl font-semibold disabled:opacity-50'

/** A bottom-sheet style dialog big enough for a driver's thumb. */
export function Sheet({ title, lang, onClose, children }: { title: string; lang: Lang; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { ref.current?.showModal() }, [])
  return (
    <dialog ref={ref} onClose={onClose} aria-label={title} className="m-0 mt-auto w-screen max-w-none rounded-t-3xl border-0 bg-surface p-0 text-ink backdrop:bg-black/40 sm:m-auto sm:w-[min(32rem,94vw)] sm:rounded-3xl">
      <div className="space-y-5 p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-2xl font-semibold">{title}</h2>
          <button type="button" onClick={() => ref.current?.close()} aria-label={translate(lang, 'common.close')} className="grid h-12 w-12 place-items-center rounded-full border border-line"><X size={22} aria-hidden /></button>
        </div>
        {children}
      </div>
    </dialog>
  )
}

export interface HandoverBody { code: string; shortage_or_damage: boolean; note: string | null }

/** The receiver reads out a 4-digit code from their shipment page; entering it proves who received the goods. Anything short or damaged is noted here, at the door. */
export function DeliveryCodeForm({ lang, send, onDone }: { lang: Lang; send: (b: HandoverBody) => Promise<void>; onDone: () => void }) {
  const tr = (k: Key) => translate(lang, k)
  const [code, setCode] = useState('')
  const [issue, setIssue] = useState(false)
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try { await send({ code, shortage_or_damage: issue, note: issue ? note.trim() : null }); onDone() }
    catch (err) { setError(err instanceof ApiError ? err.message : tr('drv.needNet')) }
    finally { setBusy(false) }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-4">
      <label className="block space-y-2">
        <span className="text-lg font-medium">{tr('drv.code')}</span>
        <input inputMode="numeric" autoComplete="one-time-code" pattern="\d{4}" maxLength={4} required value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 4))}
          className="h-20 w-full rounded-2xl border border-line bg-surface text-center text-5xl font-semibold tracking-[0.5em] outline-none focus:border-ink" />
        <span className="block text-sm text-muted">{tr('drv.codeHelp')}</span>
      </label>
      <label className="flex min-h-14 items-center gap-3 text-lg">
        <input type="checkbox" checked={issue} onChange={(e) => setIssue(e.target.checked)} className="h-6 w-6" /> {tr('drv.issue')}
      </label>
      {issue && <input aria-label={tr('drv.issueNote')} placeholder={tr('drv.issueNote')} maxLength={300} required value={note} onChange={(e) => setNote(e.target.value)} className="h-14 w-full rounded-xl border border-line bg-surface px-4 text-lg outline-none focus:border-ink" />}
      {error && <p role="alert" className="rounded-xl bg-bad-soft px-4 py-3 text-base font-medium text-bad">{error}</p>}
      <button disabled={busy || code.length !== 4 || (issue && !note.trim())} className={`${big} bg-ink text-surface`}>{tr('drv.confirmDelivery')}</button>
    </form>
  )
}

type Kind = 'delay' | 'breakdown' | 'resolved'
const REASONS: Record<Kind, string[]> = { delay: ['traffic', 'weather', 'police', 'waiting', 'rest', 'other'], breakdown: ['tyre', 'engine', 'accident', 'other'], resolved: [] }
const MINUTES = [15, 30, 60, 120, 240]

/** Tell the office and the client about a delay or a problem with the truck, with a few taps and no typing. */
export function RoadEventForm({ lang, send, onDone }: { lang: Lang; send: (b: { kind: Kind; reason: string; minutes: number | null }) => Promise<void>; onDone: () => void }) {
  const tr = (k: Key) => translate(lang, k)
  const [kind, setKind] = useState<Kind>('delay')
  const [reason, setReason] = useState('')
  const [minutes, setMinutes] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const chip = (on: boolean) => `min-h-14 rounded-xl border px-4 text-lg ${on ? 'border-ink bg-ink text-surface' : 'border-line'}`
  const ready = kind === 'resolved' || (reason !== '' && (kind === 'breakdown' || minutes !== null))

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try { await send({ kind, reason: reason || 'other', minutes: kind === 'delay' ? minutes : null }); onDone() }
    catch (err) { setError(err instanceof ApiError ? err.message : tr('drv.needNet')) }
    finally { setBusy(false) }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-5">
      <div role="group" className="grid grid-cols-3 gap-2">
        {(['delay', 'breakdown', 'resolved'] as Kind[]).map((k) => (
          <button key={k} type="button" aria-pressed={kind === k} onClick={() => { setKind(k); setReason(''); setMinutes(null) }} className={`${chip(kind === k)} text-base leading-tight`}>
            {tr(k === 'delay' ? 'drv.pDelay' : k === 'breakdown' ? 'drv.pBreak' : 'drv.pResolved')}
          </button>
        ))}
      </div>
      {REASONS[kind].length > 0 && (
        <fieldset className="space-y-2"><legend className="mb-2 text-lg font-medium">{tr('drv.pWhy')}</legend>
          <div className="flex flex-wrap gap-2">{REASONS[kind].map((r) => <button key={r} type="button" aria-pressed={reason === r} onClick={() => setReason(r)} className={chip(reason === r)}>{tr(`drv.r.${r}` as Key)}</button>)}</div>
        </fieldset>
      )}
      {kind === 'delay' && (
        <fieldset className="space-y-2"><legend className="mb-2 text-lg font-medium">{tr('drv.pHow')}</legend>
          <div className="flex flex-wrap gap-2">{MINUTES.map((m) => <button key={m} type="button" aria-pressed={minutes === m} onClick={() => setMinutes(m)} className={chip(minutes === m)}>{translate(lang, 'drv.pMin', { n: m })}</button>)}</div>
        </fieldset>
      )}
      {error && <p role="alert" className="rounded-xl bg-bad-soft px-4 py-3 text-base font-medium text-bad">{error}</p>}
      <button disabled={busy || !ready} className={`${big} bg-ink text-surface`}>{tr('drv.pSend')}</button>
    </form>
  )
}
