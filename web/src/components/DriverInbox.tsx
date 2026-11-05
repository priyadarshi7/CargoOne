import { Bell } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'

interface Item { id: string; kind: string; title: string; body: string; link: string | null; read: boolean; created_at: string }
const TXT = {
  en: { title: 'New messages', clear: 'Mark all as read' },
  hi: { title: 'नए संदेश', clear: 'सब पढ़ा हुआ करें' },
  mr: { title: 'नवीन संदेश', clear: 'सर्व वाचले म्हणून खूण करा' },
} as const

/** The driver's inbox: what the office just told them (new trip, change, cancellation). Shown only while something is unread. */
export default function DriverInbox({ onOpen }: { onOpen?: () => void }) {
  const { lang } = useI18n()
  const [data, setData] = useState<{ unread: number; items: Item[] } | null>(null)
  const x = TXT[lang]
  const load = useCallback(() => { api<{ unread: number; items: Item[] }>('/notifications/mine?limit=5').then(setData).catch(() => undefined) }, [])
  useEffect(() => {
    load()
    const every = window.setInterval(load, 60_000)
    const onVisible = () => { if (document.visibilityState === 'visible') load() }
    document.addEventListener('visibilitychange', onVisible)
    return () => { window.clearInterval(every); document.removeEventListener('visibilitychange', onVisible) }
  }, [load])

  const unread = data?.items.filter((i) => !i.read) ?? []
  if (!data || data.unread === 0) return null
  async function clear() { await api('/notifications/read-all', { method: 'POST' }); load(); window.dispatchEvent(new Event('cargoone:messages-read')) }
  return (
    <section aria-label={x.title} className="mb-4 space-y-2 rounded-2xl border border-line bg-accent-soft p-4">
      <p className="flex items-center gap-2 font-semibold text-accent"><Bell size={18} aria-hidden /> {x.title} <span className="rounded-full bg-ink px-2 text-sm text-surface">{data.unread}</span></p>
      <ul className="space-y-2">
        {unread.map((n) => (
          <li key={n.id} className="text-base">
            {n.link ? <Link to={n.link} onClick={onOpen} className="block"><b>{n.title}</b><span className="block text-muted">{n.body}</span></Link> : <><b>{n.title}</b><span className="block text-muted">{n.body}</span></>}
          </li>
        ))}
      </ul>
      <button onClick={() => void clear()} className="text-sm font-medium text-accent underline">{x.clear}</button>
    </section>
  )
}
