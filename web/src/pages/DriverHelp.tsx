import { BellOff, BellRing, Camera, CloudUpload, KeyRound, LogOut, Phone, Play, ShieldCheck, WifiOff, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import DriverShell from '../components/DriverShell'
import { ThemeChoice } from '../components/ThemeToggle'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useDriverBase } from '../lib/driverBase'
import { useSyncedQueue } from '../lib/capture/sync'
import { useI18n } from '../lib/i18n'
import { useCachedApi } from '../lib/offline/cache'
import { flushOutbox, useOutbox } from '../lib/offline/outbox'
import { usePush } from '../lib/push'

const STEPS: { icon: LucideIcon; key: 'drv.how1' | 'drv.how2' | 'drv.how3' }[] = [
  { icon: Play, key: 'drv.how1' }, { icon: Camera, key: 'drv.how2' }, { icon: WifiOff, key: 'drv.how3' },
]

/** Help for a driver: three pictured steps, alerts on or off with a test, screen colour, send what is waiting, change the PIN, sign out. */
export default function DriverHelp() {
  const { user, logout } = useAuth()
  const { link } = useDriverBase()
  const { data: office } = useCachedApi<{ phone: string | null }>('/trips/office-contact', user?.id ?? 'anon')
  const { t } = useI18n()
  const photos = useSyncedQueue()
  const { waiting } = useOutbox()
  const { state, enable, disable } = usePush()
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const pending = photos + waiting

  async function sync() {
    setBusy(true)
    await flushOutbox().catch(() => undefined)
    setBusy(false)
  }
  async function test() {
    setNote(null)
    try {
      const r = await api<{ sent: number }>('/push/test', { method: 'POST' })
      setNote(r.sent > 0 ? t('drv.alerts.testSent') : t('drv.alerts.testNone'))
    } catch { setNote(t('drv.alerts.testNone')) }
  }

  const row = 'flex h-16 w-full items-center gap-3 rounded-2xl border border-line px-4 text-lg font-medium'
  return (
    <DriverShell title={t('drv.help.title')}>
      <section aria-label={t('drv.help.how')} className="space-y-3">
        <h2 className="text-base font-semibold text-muted">{t('drv.help.how')}</h2>
        <ol className="space-y-3">
          {STEPS.map(({ icon: Icon, key }, i) => (
            <li key={key} className="flex items-center gap-4 rounded-2xl border border-line p-4">
              <span className="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-wash"><Icon size={28} aria-hidden /></span>
              <span className="text-lg leading-snug"><span className="mr-1.5 font-semibold">{i + 1}.</span>{t(key)}</span>
            </li>
          ))}
        </ol>
      </section>

      {office?.phone && <a href={`tel:${office.phone}`} className={`${'flex h-16 w-full items-center gap-3 rounded-2xl border border-line px-4 text-lg font-medium'} mt-8 bg-ink text-surface`}><Phone size={24} aria-hidden /> {t('drv.callOffice')}</a>}

      <section className="mt-8 space-y-3" aria-label={t('drv.help.alerts')}>
        <h2 className="text-base font-semibold text-muted">{t('drv.help.alerts')}</h2>
        {state === 'on' && (
          <>
            <p className="flex items-center gap-2 text-lg font-medium text-ok"><BellRing size={22} aria-hidden /> {t('drv.alerts.isOn')}</p>
            <button onClick={() => void test()} className={row}><BellRing size={24} aria-hidden /> {t('drv.alerts.test')}</button>
            <button onClick={() => void disable()} className={row}><BellOff size={24} aria-hidden /> {t('drv.alerts.off')}</button>
          </>
        )}
        {state === 'off' && <button onClick={() => void enable()} className={`${row} bg-ink text-surface`}><BellRing size={24} aria-hidden /> {t('drv.alerts.on')}</button>}
        {state === 'blocked' && <p className="rounded-2xl bg-warn-soft px-4 py-3 text-base font-medium text-warn">{t('drv.alerts.blocked')}</p>}
        {state === 'unsupported' && <p className="rounded-2xl bg-wash px-4 py-3 text-base text-muted">{t('drv.alerts.unsupported')}</p>}
        {state === 'no-server' && <p className="rounded-2xl bg-wash px-4 py-3 text-base text-muted">{t('drv.alerts.noServer')}</p>}
        {note && <p aria-live="polite" className="text-base font-medium">{note}</p>}
      </section>

      <section className="mt-8 space-y-3" aria-label={t('drv.help.theme')}>
        <h2 className="text-base font-semibold text-muted">{t('drv.help.theme')}</h2>
        <ThemeChoice />
      </section>

      <section className="mt-8 space-y-3">
        <button onClick={() => void sync()} disabled={busy || pending === 0} className={`${row} disabled:opacity-50`}>
          <CloudUpload size={24} aria-hidden /> {busy ? t('drv.sending') : pending > 0 ? `${t('drv.help.sync')} (${pending})` : t('drv.help.nothing')}
        </button>
        <Link to="/privacy" className={row}><ShieldCheck size={24} aria-hidden /> {t('priv.title')}</Link>
        {!link && <Link to="/driver/pin" className={row}><KeyRound size={24} aria-hidden /> {t('drv.help.pin')}</Link>}
        {!link && <button onClick={logout} className={row}><LogOut size={24} aria-hidden /> {t('drv.help.out')}</button>}
      </section>
    </DriverShell>
  )
}
