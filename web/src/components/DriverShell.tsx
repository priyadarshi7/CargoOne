import { CircleHelp, CloudOff, Truck, Wallet, Wifi, type LucideIcon } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useSyncedQueue } from '../lib/capture/sync'
import { LANGUAGES, useI18n } from '../lib/i18n'
import { useOnline } from '../lib/offline/online'
import { dismissFailed, useOutbox } from '../lib/offline/outbox'

const TABS: { to: string; icon: LucideIcon; key: 'drv.tabTrips' | 'drv.tabMoney' | 'drv.tabHelp'; end?: boolean }[] = [
  { to: '/driver', icon: Truck, key: 'drv.tabTrips', end: true },
  { to: '/driver/expense', icon: Wallet, key: 'drv.tabMoney' },
  { to: '/driver/help', icon: CircleHelp, key: 'drv.tabHelp' },
]
const SHORT: Record<string, string> = { en: 'EN', hi: 'हि', mr: 'म' }

/** The frame of every driver screen. Built for a cheap Android and a low-literacy driver: big icons with one short word,
 *  a bottom bar with three places, no blur or shadows, and one honest line about the network.
 *  It also keeps the offline queues draining (photos, trip starts, expenses) on every driver page. */
export default function DriverShell({ children, title }: { children: ReactNode; title?: string }) {
  const { user } = useAuth()
  const { t, lang, setLang } = useI18n()
  const online = useOnline()
  const photos = useSyncedQueue()
  const { waiting, failed } = useOutbox()
  const pending = photos + waiting

  useEffect(() => { // first visit: the language the office chose for this driver; after that, whatever they pick
    try { if (user && !localStorage.getItem('cargoone.lang')) setLang(user.language) } catch { /* storage blocked: stays English */ }
  }, [user, setLang])

  return (
    <div className="mx-auto flex min-h-full max-w-md flex-col">
      <header className="sticky top-0 z-10 border-b border-line bg-surface px-4 pb-3 pt-3">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-ink text-surface"><Truck size={20} aria-hidden /></span>
          <div className="min-w-0 flex-1 leading-tight">
            <h1 className="truncate text-lg font-semibold">{title ?? user?.name}</h1>
            <p className={`flex items-center gap-1.5 text-sm ${online ? 'text-muted' : 'font-medium text-warn'}`} aria-live="polite">
              {online ? <Wifi size={14} aria-hidden /> : <CloudOff size={14} aria-hidden />}
              {pending > 0 ? t('drv.waiting', { n: pending }) : online ? t('drv.online') : t('drv.offline')}
            </p>
          </div>
          <div className="flex gap-1" role="group" aria-label={t('drv.help.lang')}>
            {LANGUAGES.map(([v]) => (
              <button key={v} onClick={() => setLang(v)} aria-pressed={lang === v} aria-label={LANGUAGES.find(([x]) => x === v)?.[1]}
                className={`grid h-11 w-11 place-items-center rounded-xl text-base font-semibold ${lang === v ? 'bg-ink text-surface' : 'border border-line text-muted'}`}>{SHORT[v]}</button>
            ))}
          </div>
        </div>
      </header>

      <main className="flex-1 px-4 pb-28 pt-5">
        {failed.map((f) => (
          <p key={f.id} role="alert" className="mb-4 flex items-center justify-between gap-3 rounded-xl bg-bad-soft px-4 py-3 text-base font-medium text-bad">
            <span>{t('drv.failed', { why: f.error ?? '' })}</span>
            <button onClick={() => void dismissFailed(f.id)} className="h-10 shrink-0 rounded-lg border border-bad px-3 text-sm">{t('drv.dismiss')}</button>
          </p>
        ))}
        {children}
      </main>

      <nav aria-label="Driver" className="fixed inset-x-0 bottom-0 z-10 border-t border-line bg-surface">
        <div className="mx-auto grid max-w-md grid-cols-3 px-2 pb-2 pt-1.5">
          {TABS.map(({ to, icon: Icon, key, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `flex min-h-16 flex-col items-center justify-center gap-1 rounded-xl text-sm font-semibold ${isActive ? 'text-ink' : 'text-muted'}`}>
              {({ isActive }) => (<><span className={`grid h-9 w-14 place-items-center rounded-full ${isActive ? 'bg-wash' : ''}`}><Icon size={24} aria-hidden /></span>{t(key)}</>)}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
