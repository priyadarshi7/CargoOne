import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import { Table } from './ui'

interface Item { id: string; at: string; driver: string | null; to: string | null; template: 'welcome' | 'trip_assigned' | 'trip_update'; status: 'sent' | 'simulated' | 'failed' | 'skipped'; error: string | null; text: string }
const TONE = { sent: 'text-ok', simulated: 'text-warn', failed: 'text-bad', skipped: 'text-muted' } as const

/** Everything the system tried to send to drivers on WhatsApp, with the result: the place to look when "I never got the message". */
export default function MessagesTab() {
  const { t, lang } = useI18n()
  const [data, setData] = useState<{ live: boolean; items: Item[] } | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => { api<{ live: boolean; items: Item[] }>('/messages').then(setData).catch(() => setError(true)) }, [])
  if (error) return <p className="text-bad">{t('setup.loadFail')}</p>
  if (!data) return <p className="text-muted">{t('common.loading')}</p>
  const when = (iso: string) => new Date(iso).toLocaleString(lang === 'en' ? 'en-IN' : `${lang}-IN`, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
  return (
    <div className="space-y-4">
      {!data.live && <p className="rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn">{t('notif.log.banner')}</p>}
      <Table head={[t('notif.log.when'), t('drv.name'), t('notif.log.what'), t('notif.log.status')]} empty={data.items.length ? undefined : t('notif.log.empty')}>
        {data.items.map((m) => (
          <tr key={m.id} className="border-t border-line align-top">
            <td className="whitespace-nowrap px-4 py-3 text-muted">{when(m.at)}</td>
            <td className="px-4 py-3">{m.driver ?? '—'}<div className="text-xs text-muted tabular-nums">{m.to}</div></td>
            <td className="px-4 py-3"><div className="font-medium">{t(`notif.tpl.${m.template}`)}</div><div className="max-w-md text-xs text-muted">{m.text}</div></td>
            <td className={`px-4 py-3 ${TONE[m.status]}`}>{t(`notif.status.${m.status}`)}{m.error && <div className="text-xs">{m.error}</div>}</td>
          </tr>
        ))}
      </Table>
    </div>
  )
}
