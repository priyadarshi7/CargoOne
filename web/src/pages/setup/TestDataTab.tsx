import { TriangleAlert } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import { inputCls } from './ui'

const KEYS = ['drivers', 'trucks', 'vendors', 'clients', 'trips', 'pods', 'papers', 'requests', 'messages'] as const

/** Development only: wipe the test data to try the product from day zero. The tab is not offered when the server is not in development mode. */
export default function TestDataTab() {
  const { t } = useI18n()
  const [counts, setCounts] = useState<Record<string, number> | null>(null)
  const [word, setWord] = useState('')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const load = () => api<{ counts: Record<string, number> }>('/devtools/test-data').then((r) => setCounts(r.counts)).catch(() => setCounts(null))
  useEffect(() => { void load() }, [])

  async function wipe(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setMsg(null)
    try {
      await api('/devtools/reset-test-data', { method: 'POST', body: JSON.stringify({ confirm: word }) })
      setMsg({ ok: true, text: t('reset.done') })
      setWord('')
      await load()
    } catch (err) { setMsg({ ok: false, text: err instanceof ApiError ? err.message : t('reset.fail') }) } finally { setBusy(false) }
  }

  if (!counts) return <p className="text-muted">{t('common.loading')}</p>
  return (
    <form onSubmit={(e) => void wipe(e)} className="max-w-xl space-y-5">
      <h2 className="text-lg font-semibold">{t('reset.title')}</h2>
      <p className="flex items-start gap-2 rounded-lg bg-bad-soft px-3 py-2 text-sm text-bad"><TriangleAlert size={16} className="mt-0.5 shrink-0" aria-hidden /> {t('reset.warn')}</p>
      <dl className="grid grid-cols-3 gap-3 text-sm">
        {KEYS.map((k) => <div key={k} className="rounded-xl border border-line p-3"><dt className="text-xs text-muted">{t(`reset.${k}`)}</dt><dd className="text-xl font-semibold tabular-nums">{counts[k] ?? 0}</dd></div>)}
      </dl>
      <label className="block space-y-1 text-sm"><span className="font-medium">{t('reset.type')}</span>
        <input className={inputCls} value={word} onChange={(e) => setWord(e.target.value)} autoComplete="off" /></label>
      <button disabled={busy || word.trim() !== 'DELETE'} className="rounded-lg bg-bad px-4 py-2 text-sm font-medium text-on-solid disabled:opacity-50">{t('reset.go')}</button>
      {msg && <p role={msg.ok ? 'status' : 'alert'} className={`text-sm ${msg.ok ? 'text-ok' : 'text-bad'}`}>{msg.text}</p>}
    </form>
  )
}
