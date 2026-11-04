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

  if (error) return <p className="text-bad">{t('drv.error')}</p>
  if (!drivers) return <p className="text-muted">{t('common.loading')}</p>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t('drv.title')}</h1>
        <p className="text-sm text-muted">{t('drv.sub')}</p>
      </div>
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="bg-wash text-muted"><tr>{(['drv.name', 'drv.phone', 'drv.branch', 'drv.status', ''] as const).map((h) => <th key={h} className="px-4 py-3 font-medium">{h && t(h)}</th>)}</tr></thead>
          <tbody>
            {drivers.map((d) => (
              <tr key={d.id} className="border-t border-line">
                <td className="px-4 py-3 font-medium">{d.name}</td>
                <td className="px-4 py-3 tabular-nums">{d.phone ?? '—'}</td>
                <td className="px-4 py-3">{d.branch ?? '—'}</td>
                <td className="px-4 py-3">
                  {d.locked ? <span className="inline-flex items-center gap-1 text-bad"><Lock size={14} aria-hidden /> {t('drv.locked')}</span>
                    : d.must_change_pin ? <span className="text-warn">{t('drv.temp')}</span> : <span className="text-muted">{t('drv.ok')}</span>}
                </td>
                <td className="px-4 py-3 text-right">
                  <button onClick={() => setConfirm(d)} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium hover:border-accent hover:text-accent">
                    <KeyRound size={14} aria-hidden /> {t('drv.reset')}
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
  const { t } = useI18n()
  const { ref, props } = useModal(onClose)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function go() {
    setBusy(true)
    try { onDone((await api<{ pin: string }>(`/drivers/${driver.id}/reset-pin`, { method: 'POST' })).pin) }
    catch (e) { setError(e instanceof ApiError ? e.message : t('drv.resetFail')); setBusy(false) }
  }
  return (
    <dialog {...props} aria-label="Reset PIN" className={box}>
      <div className="space-y-4 p-6">
        <h2 className="text-lg font-semibold">{t('drv.confirmTitle', { name: driver.name })}</h2>
        <p className="text-sm text-muted">{t('drv.confirmBody', { name: driver.name })}</p>
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
        <div className="flex justify-end gap-3">
          <button onClick={() => ref.current?.close()} className="rounded-lg border border-line px-4 py-2 text-sm">{t('common.cancel')}</button>
          <button disabled={busy} onClick={() => void go()} className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-on-solid disabled:opacity-60">{busy ? t('drv.resetting') : t('drv.reset')}</button>
        </div>
      </div>
    </dialog>
  )
}

function PinDialog({ driver, pin, onClose }: { driver: Driver; pin: string; onClose: () => void }) {
  const { t } = useI18n()
  const { ref, props } = useModal(onClose)
  return (
    <dialog {...props} aria-label="Temporary PIN" className={box}>
      <div className="space-y-5 p-6 text-center">
        <div className="flex justify-end"><button onClick={() => ref.current?.close()} aria-label={t('common.close')} className="text-muted hover:text-ink"><X size={20} /></button></div>
        <p className="text-sm text-muted">{t('drv.tempFor', { name: driver.name })}</p>
        <p className="text-5xl font-semibold tabular-nums tracking-[0.25em]" aria-label="Temporary PIN digits">{pin}</p>
        <p className="text-sm text-muted">{t('drv.tempNote')}</p>
      </div>
    </dialog>
  )
}
