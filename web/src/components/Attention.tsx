import { ArrowRight, BellRing, CircleCheck, FileClock, FileWarning, IdCard, ReceiptText, ScanSearch, Truck, type LucideIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'

type Key = 'missing_pod' | 'review_waiting' | 'unbilled' | 'expenses_pending' | 'papers' | 'licences'
interface Item { key: Key; count: number; oldest_days: number | null; to: string; severity: 'high' | 'medium' | 'low' }
interface Reminded { sent: number; skipped_recent: number; no_phone: number; no_driver: number; simulated: boolean }

const ICON: Record<Key, LucideIcon> = { missing_pod: FileWarning, review_waiting: ScanSearch, unbilled: FileClock, expenses_pending: ReceiptText, papers: Truck, licences: IdCard }
const TONE = { high: 'bg-bad-soft text-bad', medium: 'bg-warn-soft text-warn', low: 'bg-wash text-muted' } as const

/** The short list of things waiting on a person, shown at the top of the ops dashboard and the billing screen. */
export default function Attention() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [items, setItems] = useState<Item[] | null>(null)
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const canSend = user?.role === 'ops' || user?.role === 'billing' || user?.role === 'admin'

  useEffect(() => { api<{ items: Item[] }>('/attention').then((r) => setItems(r.items)).catch(() => setError(true)) }, [])

  async function remind() {
    setBusy(true)
    setNote(null)
    try {
      const r = await api<Reminded>('/attention/remind-drivers', { method: 'POST' })
      setNote(`${t('attn.reminded', { sent: r.sent, skipped: r.skipped_recent, nophone: r.no_phone, nodriver: r.no_driver })}${r.simulated ? ' ' + t('attn.simulated') : ''}`)
    } catch (e) { setNote(e instanceof ApiError ? e.message : t('attn.fail')) } finally { setBusy(false) }
  }

  if (error) return <p className="text-sm text-bad">{t('attn.loadFail')}</p>
  if (!items) return null
  return (
    <section aria-label={t('attn.title')} className="rounded-xl border border-line p-5">
      <h2 className="font-semibold">{t('attn.title')}</h2>
      {items.length === 0 ? (
        <p className="mt-3 flex items-center gap-2 text-sm text-ok"><CircleCheck size={18} aria-hidden /> {t('attn.empty')}</p>
      ) : (
        <ul className="mt-3 divide-y divide-line">
          {items.map((i) => {
            const Icon = ICON[i.key]
            return (
              <li key={i.key} className="flex flex-wrap items-center gap-3 py-3">
                <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-full ${TONE[i.severity]}`}><Icon size={18} aria-hidden /></span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{t(`attn.${i.key}`, { n: i.count })}</p>
                  {i.oldest_days !== null && i.oldest_days > 0 && <p className="text-xs text-muted">{t('attn.oldest', { n: i.oldest_days })}</p>}
                </div>
                {i.key === 'missing_pod' && canSend && (
                  <button disabled={busy} onClick={() => void remind()} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-medium hover:border-accent hover:text-accent disabled:opacity-60">
                    <BellRing size={14} aria-hidden /> {busy ? t('attn.reminding') : t('attn.remind')}
                  </button>
                )}
                <Link to={i.to} className="inline-flex items-center gap-1 text-xs font-medium text-accent">{t('attn.go')} <ArrowRight size={14} aria-hidden /></Link>
              </li>
            )
          })}
        </ul>
      )}
      {note && <p role="status" className="mt-3 text-sm text-muted">{note}</p>}
    </section>
  )
}
