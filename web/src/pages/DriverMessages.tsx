import { Bell, BellDot, Camera, CheckCheck, CircleCheck, CircleX, Truck, UserRoundCheck, type LucideIcon } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import DriverShell from '../components/DriverShell'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useCachedApi } from '../lib/offline/cache'

interface Item { id: string; kind: string; title: string; body: string; link: string | null; read: boolean; created_at: string }
interface Box { unread: number; items: Item[] }
const ICON: Record<string, LucideIcon> = { welcome: UserRoundCheck, trip_assigned: Truck, trip_update: Truck, expense_approved: CircleCheck, expense_rejected: CircleX, pod_retake: Camera }

/** Everything the office has told this driver, newest first, unread ones marked. Tapping one opens the trip it is about. Works offline (the phone's saved copy). */
export default function DriverMessages() {
  const { user } = useAuth()
  const { t, date } = useI18n()
  const nav = useNavigate()
  const { data, stale, loaded, mutate, reload } = useCachedApi<Box>('/notifications/mine?limit=50', user?.id ?? 'anon')

  const changed = () => window.dispatchEvent(new Event('cargoone:messages-read'))
  async function open(m: Item) {
    if (!m.read) {
      mutate((b) => ({ unread: Math.max(0, b.unread - 1), items: b.items.map((x) => (x.id === m.id ? { ...x, read: true } : x)) }))
      await api(`/notifications/${m.id}/read`, { method: 'POST' }).then(changed).catch(() => undefined)
    }
    if (m.link) nav(m.link)
  }
  async function readAll() {
    mutate((b) => ({ unread: 0, items: b.items.map((x) => ({ ...x, read: true })) }))
    await api('/notifications/read-all', { method: 'POST' }).then(changed).catch(() => reload())
  }

  const items = data?.items ?? []
  return (
    <DriverShell title={t('drv.msg.title')}>
      {stale && <p aria-live="polite" className="mb-4 rounded-xl bg-warn-soft px-4 py-3 text-base font-medium text-warn">{t('drv.stale')}</p>}
      {loaded && items.length === 0 && (
        <section className="grid place-items-center gap-3 rounded-3xl border border-line px-6 py-14 text-center">
          <span className="grid h-20 w-20 place-items-center rounded-full bg-wash text-muted"><Bell size={40} aria-hidden /></span>
          <p className="text-xl font-semibold">{t('drv.msg.empty')}</p>
          <p className="text-base text-muted">{t('drv.msg.emptyB')}</p>
        </section>
      )}
      {(data?.unread ?? 0) > 0 && (
        <button onClick={() => void readAll()} className="mb-4 flex h-14 w-full items-center justify-center gap-2 rounded-2xl border border-line text-lg font-medium"><CheckCheck size={22} aria-hidden /> {t('drv.msg.markAll')}</button>
      )}
      <ul className="space-y-3">
        {items.map((m) => {
          const Icon = m.read ? (ICON[m.kind] ?? Bell) : BellDot
          return (
            <li key={m.id}>
              <button onClick={() => void open(m)} className={`flex w-full items-start gap-4 rounded-2xl border p-4 text-left ${m.read ? 'border-line' : 'border-ink bg-wash'}`}>
                <span className={`mt-0.5 grid h-12 w-12 shrink-0 place-items-center rounded-full ${m.read ? 'bg-wash text-muted' : 'bg-ink text-surface'}`}><Icon size={24} aria-hidden /></span>
                <span className="min-w-0 flex-1">
                  <span className={`block text-lg leading-snug ${m.read ? 'font-medium' : 'font-semibold'}`}>{m.title}</span>
                  <span className="mt-0.5 block break-words text-base text-muted">{m.body}</span>
                  <span className="mt-1.5 block text-sm text-muted">{date(m.created_at, true)}</span>
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </DriverShell>
  )
}
