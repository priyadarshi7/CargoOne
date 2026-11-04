import { KeyRound, Lock, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../lib/api'
import { useI18n } from '../lib/i18n'

interface Driver { id: string; name: string; phone: string | null; branch: string | null; locked: boolean; must_change_pin: boolean }

/** Office tool: when a driver forgets their PIN, issue a temporary one to read out over the phone. */
export default function Drivers() {
  const { t } = useI18n()
  const [drivers, setDrivers] = useState<Driver[] | null>(null)
  const [error, setError] = useState(false)
  const [confirm, setConfirm] = useState<Driver | null>(null)
  const [issued, setIssued] = useState<{ driver: Driver; pin: string } | null>(null)

  const load = () => api<Driver[]>('/drivers').then(setDrivers).catch(() => setError(true))
  useEffect(() => { void load() }, [])

  if (error) return <p className="text-bad">Could not load drivers.</p>
  if (!drivers) return <p className="text-muted">{t('common.loading')}</p>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Drivers</h1>
        <p className="text-sm text-muted">A driver forgot their PIN? Reset it here, then read the temporary PIN to them. They choose their own at the next sign-in.</p>
      </div>
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="bg-wash text-muted"><tr>{['Name', 'Phone', 'Branch', 'Status', ''].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr></thead>
          <tbody>
            {drivers.map((d) => (
              <tr key={d.id} className="border-t border-line">
                <td className="px-4 py-3 font-medium">{d.name}</td>
                <td className="px-4 py-3 tabular-nums">{d.phone ?? '—'}</td>
                <td className="px-4 py-3">{d.branch ?? '—'}</td>
                <td className="px-4 py-3">
                  {d.locked ? <span className="inline-flex items-center gap-1 text-bad"><Lock size={14} aria-hidden /> Locked</span>
                    : d.must_change_pin ? <span className="text-warn">Has a temporary PIN</span> : <span className="text-muted">OK</span>}
                </td>
                <td className="px-4 py-3 text-right">
                  <button onClick={() => setConfirm(d)} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium hover:border-accent hover:text-accent">
                    <KeyRound size={14} aria-hidden /> Reset PIN
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {confirm && <ResetDialog driver={confirm} onClose={() => setConfirm(null)} onDone={(pin) => { setIssued({ driver: confirm, pin }); setConfirm(null); void load() }} />}
      {issued && <PinDialog {...issued} onClose={() => setIssued(null)} />}
    </div>
  )
}

function useModal(onClose: () => void) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { ref.current?.showModal() }, [])
  return { ref, props: { ref, onClose } }
}
const box = 'm-auto w-[min(26rem,92vw)] rounded-2xl border border-line p-0 shadow-xl backdrop:bg-black/30'

function ResetDialog({ driver, onClose, onDone }: { driver: Driver; onClose: () => void; onDone: (pin: string) => void }) {
  const { ref, props } = useModal(onClose)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function go() {
    setBusy(true)
    try { onDone((await api<{ pin: string }>(`/drivers/${driver.id}/reset-pin`, { method: 'POST' })).pin) }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Could not reset the PIN.'); setBusy(false) }
  }
  return (
    <dialog {...props} aria-label="Reset PIN" className={box}>
      <div className="space-y-4 p-6">
        <h2 className="text-lg font-semibold">Reset {driver.name}&apos;s PIN?</h2>
        <p className="text-sm text-muted">Their old PIN stops working and any phone they are signed in on is signed out. Check you are speaking to {driver.name} before you read out the new PIN.</p>
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
        <div className="flex justify-end gap-3">
          <button onClick={() => ref.current?.close()} className="rounded-lg border border-line px-4 py-2 text-sm">Cancel</button>
          <button disabled={busy} onClick={() => void go()} className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-60">{busy ? 'Resetting…' : 'Reset PIN'}</button>
        </div>
      </div>
    </dialog>
  )
}

function PinDialog({ driver, pin, onClose }: { driver: Driver; pin: string; onClose: () => void }) {
  const { ref, props } = useModal(onClose)
  return (
    <dialog {...props} aria-label="Temporary PIN" className={box}>
      <div className="space-y-5 p-6 text-center">
        <div className="flex justify-end"><button onClick={() => ref.current?.close()} aria-label="Close" className="text-muted hover:text-ink"><X size={20} /></button></div>
        <p className="text-sm text-muted">Temporary PIN for {driver.name}</p>
        <p className="text-5xl font-semibold tabular-nums tracking-[0.25em]" aria-label="Temporary PIN digits">{pin}</p>
        <p className="text-sm text-muted">Read it out now. It is shown only once and cannot be looked up later. The driver will be asked to choose their own PIN after signing in with it.</p>
      </div>
    </dialog>
  )
}
