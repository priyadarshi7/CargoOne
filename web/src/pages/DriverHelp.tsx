import { Camera, CloudUpload, KeyRound, LogOut, Play, WifiOff, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import DriverShell from '../components/DriverShell'
import { useAuth } from '../lib/auth'
import { useSyncedQueue } from '../lib/capture/sync'
import { useI18n } from '../lib/i18n'
import { flushOutbox, useOutbox } from '../lib/offline/outbox'

const STEPS: { icon: LucideIcon; key: 'drv.how1' | 'drv.how2' | 'drv.how3' }[] = [
  { icon: Play, key: 'drv.how1' }, { icon: Camera, key: 'drv.how2' }, { icon: WifiOff, key: 'drv.how3' },
]

/** Help for a driver: three pictures with one sentence each, send what is waiting, change the PIN, sign out. */
export default function DriverHelp() {
  const { logout } = useAuth()
  const { t } = useI18n()
  const photos = useSyncedQueue()
  const { waiting } = useOutbox()
  const [busy, setBusy] = useState(false)
  const pending = photos + waiting

  async function sync() {
    setBusy(true)
    await flushOutbox().catch(() => undefined)
    setBusy(false)
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

      <section className="mt-8 space-y-3">
        <button onClick={() => void sync()} disabled={busy || pending === 0} className={`${row} disabled:opacity-50`}>
          <CloudUpload size={24} aria-hidden /> {busy ? t('drv.sending') : pending > 0 ? `${t('drv.help.sync')} (${pending})` : t('drv.help.nothing')}
        </button>
        <Link to="/driver/pin" className={row}><KeyRound size={24} aria-hidden /> {t('drv.help.pin')}</Link>
        <button onClick={logout} className={row}><LogOut size={24} aria-hidden /> {t('drv.help.out')}</button>
      </section>
    </DriverShell>
  )
}
