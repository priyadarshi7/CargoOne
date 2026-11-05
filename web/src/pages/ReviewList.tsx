import { CircleCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ReasonChips } from '../components/ReasonChips'
import { api, type ReviewItem } from '../lib/api'
import { useI18n, type Key } from '../lib/i18n'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const ago = (iso: string, t: (k: Key, v?: Record<string, number>) => string) => {
  const h = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 3_600_000))
  return h < 48 ? t('review.hoursAgo', { n: h }) : t('review.daysAgo', { n: Math.round(h / 24) })
}

export default function ReviewList() {
  const { t } = useI18n()
  const [items, setItems] = useState<ReviewItem[] | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    api<ReviewItem[]>('/review').then(setItems).catch(() => setError(true))
  }, [])

  if (error) return <p className="text-bad">{t('review.error')}</p>
  if (!items) return <p className="text-muted">{t('common.loading')}</p>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">{t('review.title')}</h1>
        <p className="text-sm text-muted">{t('review.sub')}</p>
      </div>
      {items.length === 0 ? (
        <div className="grid place-items-center gap-3 rounded-xl border border-line py-16 text-muted">
          <CircleCheck size={40} className="text-ok" aria-hidden /> {t('review.empty')}
        </div>
      ) : (
        <ul className="divide-y divide-line rounded-xl border border-line">
          {items.map((it) => (
            <li key={it.trip_id}>
              <Link to={`/office/review/${it.trip_id}`} className="flex flex-wrap items-center gap-x-6 gap-y-2 px-5 py-4 hover:bg-wash">
                <div className="min-w-40">
                  <div className="font-medium">{it.trip_code}</div>
                  <div className="text-sm text-muted">{it.client} · {it.destination}</div>
                </div>
                <div className="flex-1"><ReasonChips reasons={it.reasons} /></div>
                <div className="text-right text-sm">
                  <div className="tabular-nums">{inr.format(it.freight_amount)}</div>
                  <div className="text-muted">{ago(it.captured_at, t)}</div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
