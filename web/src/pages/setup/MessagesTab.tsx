import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { useI18n } from '../../lib/i18n'
import { FilterBar, NoMatch, type FilterSelect } from '../../components/FilterBar'
import { hit, useFilters } from '../../lib/filters'
import { btnPrimary, inputCls, Table } from './ui'

interface Item {
  id: string; at: string; channel: 'whatsapp' | 'email'; driver: string | null; to: string | null
  template: 'welcome' | 'trip_assigned' | 'trip_update' | 'request_received' | 'request_update' | 'test'; status: 'sent' | 'simulated' | 'failed' | 'skipped'; error: string | null; text: string
}
interface Log { live: boolean; email_live: boolean; items: Item[] }
const TONE = { sent: 'text-ok', simulated: 'text-warn', failed: 'text-bad', skipped: 'text-muted' } as const

/** Everything the system tried to send (WhatsApp and email), with the result: the place to look when "I never got the message". */
export default function MessagesTab() {
  const { t, lang } = useI18n()
  const { user } = useAuth()
  const canTest = user?.role === 'ops' || user?.role === 'admin'
  const [data, setData] = useState<Log | null>(null)
  const { values: f, set, clear, active } = useFilters({ q: '', channel: '', status: '' })
  const [error, setError] = useState(false)
  const [to, setTo] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ tone: string; text: string } | null>(null)
  const load = useCallback(() => { api<Log>('/messages').then(setData).catch(() => setError(true)) }, [])
  useEffect(() => { load() }, [load])

  async function test(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setResult(null)
    try {
      const r = await api<{ status: 'sent' | 'simulated' | 'failed'; error: string | null }>('/messages/test-email', { method: 'POST', body: JSON.stringify({ to }) })
      setResult(r.status === 'sent' ? { tone: 'text-ok', text: t('mail.sent') } : r.status === 'simulated' ? { tone: 'text-warn', text: t('mail.simulated') } : { tone: 'text-bad', text: t('mail.failed', { error: r.error ?? '' }) })
      load()
    } catch (err) { setResult({ tone: 'text-bad', text: err instanceof ApiError ? err.message : t('mail.fail') }) } finally { setBusy(false) }
  }

  if (error) return <p className="text-bad">{t('setup.loadFail')}</p>
  if (!data) return <p className="text-muted">{t('common.loading')}</p>
  const shown = data.items.filter((m) => hit(f.q, m.driver, m.to, m.text, t(`notif.tpl.${m.template}`)) && (!f.channel || m.channel === f.channel) && (!f.status || m.status === f.status))
  const selects: FilterSelect[] = [
    { key: 'channel', label: t('notif.log.to'), value: f.channel, onChange: (v) => set('channel', v), options: [['', t('filter.allChannels')], ['whatsapp', t('notif.channel.whatsapp')], ['email', t('notif.channel.email')]] },
    { key: 'status', label: t('notif.log.status'), value: f.status, onChange: (v) => set('status', v), options: [['', t('filter.allResults')], ...(['sent', 'simulated', 'failed', 'skipped'] as const).map((s): [string, string] => [s, `${t(`notif.status.${s}`)} (${data.items.filter((m) => m.status === s).length})`])] },
  ]
  const when = (iso: string) => new Date(iso).toLocaleString(lang === 'en' ? 'en-IN' : `${lang}-IN`, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
  return (
    <div className="space-y-4">
      {!data.live && <p className="rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn">{t('notif.log.banner')}</p>}
      {!data.email_live && <p className="rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn">{t('notif.log.emailBanner')}</p>}
      {canTest && (
        <form onSubmit={(e) => void test(e)} className="flex flex-wrap items-end gap-3 rounded-xl border border-line p-4">
          <label className="min-w-64 flex-1 space-y-1 text-sm"><span className="font-medium">{t('mail.testTitle')}</span>
            <input type="email" required className={inputCls} value={to} onChange={(e) => setTo(e.target.value)} autoComplete="email" />
            <span className="block text-xs text-muted">{t('mail.testHint')}</span></label>
          <button disabled={busy} className={btnPrimary}>{busy ? t('mail.sending') : t('mail.send')}</button>
          {result && <p role="status" className={`w-full text-sm ${result.tone}`}>{result.text}</p>}
        </form>
      )}
      <FilterBar q={f.q} onQ={(v) => set('q', v)} placeholder={t('filter.messages')} selects={selects} shown={shown.length} total={data.items.length} active={active} onClear={clear} />
      {shown.length === 0 && data.items.length > 0 && <NoMatch onClear={clear} />}
      <Table head={[t('notif.log.when'), t('notif.log.to'), t('notif.log.what'), t('notif.log.status')]} empty={data.items.length ? undefined : t('notif.log.empty')}>
        {shown.map((m) => (
          <tr key={m.id} className="border-t border-line align-top">
            <td className="whitespace-nowrap px-4 py-3 text-muted">{when(m.at)}</td>
            <td className="px-4 py-3">{m.driver ?? '—'}<div className="text-xs tabular-nums text-muted">{t(`notif.channel.${m.channel}`)} · {m.to}</div></td>
            <td className="px-4 py-3"><div className="font-medium">{t(`notif.tpl.${m.template}`)}</div><div className="max-w-md whitespace-pre-line text-xs text-muted">{m.text}</div></td>
            <td className={`px-4 py-3 ${TONE[m.status]}`}>{t(`notif.status.${m.status}`)}{m.error && <div className="text-xs">{m.error}</div>}</td>
          </tr>
        ))}
      </Table>
    </div>
  )
}
