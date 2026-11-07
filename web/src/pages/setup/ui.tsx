import { X } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { ApiError } from '../../lib/api'
import { useI18n } from '../../lib/i18n'

export const inputCls = 'w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent'
export const btnPrimary = 'rounded-lg bg-ink px-4 py-2 text-sm font-medium text-surface disabled:opacity-60'
export const btnGhost = 'rounded-lg border border-line px-3 py-1.5 text-xs font-medium hover:border-accent hover:text-accent'

/** A small spinner for a button that is working. */
export function Spin() {
  return <span aria-hidden className="mr-2 inline-block size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent align-[-2px]" />
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const { t } = useI18n()
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { ref.current?.showModal() }, [])
  return (
    <dialog ref={ref} onClose={onClose} aria-label={title} className={`m-auto max-h-[92vh] ${wide ? 'w-[min(42rem,94vw)]' : 'w-[min(28rem,92vw)]'} rounded-2xl border border-line bg-surface p-0 text-ink shadow-xl backdrop:bg-black/30`}>
      <div className="space-y-4 p-6">
        <div className="flex items-start justify-between gap-4">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button onClick={() => ref.current?.close()} aria-label={t('setup.close')} className="text-muted hover:text-ink"><X size={20} /></button>
        </div>
        {children}
      </div>
    </dialog>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="block text-xs text-muted">{hint}</span>}
    </label>
  )
}

/** A form inside a Modal: runs `onSubmit`, shows the API's own sentence on failure, closes on success. */
export function FormModal({ title, onClose, onSubmit, children, submitLabel, wide }: {
  title: string; onClose: () => void; onSubmit: () => Promise<void>; children: ReactNode; submitLabel?: string; wide?: boolean
}) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try { await onSubmit() } catch (err) { setError(err instanceof ApiError ? err.message : t('setup.saveFail')); setBusy(false) }
  }
  return (
    <Modal title={title} onClose={onClose} wide={wide}>
      <form onSubmit={(e) => void submit(e)} className="space-y-4">
        {children}
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
        <div className="flex justify-end gap-3">
          <button type="button" onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-sm">{t('setup.cancel')}</button>
          <button disabled={busy} className={btnPrimary}>{busy && <Spin />}{busy ? t('setup.saving') : (submitLabel ?? t('setup.save'))}</button>
        </div>
      </form>
    </Modal>
  )
}

export function Secret({ title, note, value, onClose }: { title: string; note: string; value: string; onClose: () => void }) {
  const { t } = useI18n()
  return (
    <Modal title={title} onClose={onClose}>
      <p className="text-sm text-muted">{note}</p>
      <p className="select-all break-all rounded-xl bg-wash p-4 text-center text-3xl font-semibold tabular-nums tracking-wider" aria-label="One-time secret">{value}</p>
      <div className="flex justify-end"><button onClick={onClose} className={btnPrimary}>{t('setup.close')}</button></div>
    </Modal>
  )
}

export function Table({ head, children, empty }: { head: string[]; children: ReactNode; empty?: string }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className="w-full min-w-[620px] text-left text-sm">
        <thead className="bg-wash text-muted"><tr>{head.map((h, i) => <th key={i} className="px-4 py-3 font-medium">{h}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
      {empty && <p className="px-4 py-6 text-center text-sm text-muted">{empty}</p>}
    </div>
  )
}

export function StatusPill({ active }: { active: boolean }) {
  const { t } = useI18n()
  return <span className={active ? 'text-ok' : 'text-muted'}>{active ? t('setup.active') : t('setup.inactive')}</span>
}

/** A read-only list of label/value pairs for a details view. Empty values show a dash. */
export function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
      {rows.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="text-xs text-muted">{k}</dt>
          <dd className="break-words font-medium">{v === null || v === undefined || v === '' ? '—' : v}</dd>
        </div>
      ))}
    </dl>
  )
}
