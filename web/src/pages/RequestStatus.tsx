import { CircleCheck, CircleX } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { BASE } from '../lib/api'
import { useI18n, type Lang } from '../lib/i18n'
import { PublicFrame } from './RequestTransport'

interface Status {
  reference: string; status: 'new' | 'accepted' | 'booked' | 'declined'; company_name: string; origin: string; destination: string; material: string
  weight_tonnes: number | null; pickup_date: string; reply: string | null; quote_amount: number | null; trip_code: string | null; planned_start: string | null; language: Lang
}

/** What a requester sees at their private link: where the request stands. No contact details, nothing about anyone else. */
export default function RequestStatus() {
  const { token = '' } = useParams()
  const { t, setLang } = useI18n()
  const [data, setData] = useState<Status | 'dead' | null>(null)
  useEffect(() => {
    fetch(`${BASE}/public/requests/${encodeURIComponent(token)}`).then(async (r) => {
      if (!r.ok) return setData('dead')
      const d = (await r.json()) as Status
      setData(d)
      if (!localStorage.getItem('cargoone.lang')) setLang(d.language) // their own language, unless they already chose one
    }).catch(() => setData('dead'))
  }, [token, setLang])

  if (data === null) return <PublicFrame><p className="text-muted">…</p></PublicFrame>
  if (data === 'dead') return <PublicFrame><p role="alert" className="text-lg">{t('req.notFound')}</p><p className="mt-4"><Link to="/request" className="underline">{t('login.request')}</Link></p></PublicFrame>
  const order = ['new', 'accepted', 'booked'] as const
  const at = data.status === 'declined' ? -1 : order.indexOf(data.status)
  return (
    <PublicFrame>
      <div className="space-y-6">
        <div className="space-y-2">
          <p className="text-sm text-muted">{t('req.reference')} <b className="font-mono tabular-nums text-ink">{data.reference}</b></p>
          <h1 role="status" className="text-3xl font-semibold tracking-tight">{t(`req.st.${data.status}`, { trip: data.trip_code ?? '' })}</h1>
        </div>
        {data.status === 'declined'
          ? <p className="inline-flex items-center gap-2 rounded-full bg-bad-soft px-3 py-1 text-sm font-medium text-bad"><CircleX size={16} aria-hidden /> {t('req.status.declined')}</p>
          : (
            <ol className="rounded-2xl border border-line p-6">
              {order.map((k, i) => (
                <li key={k} className="flex gap-3.5">
                  <span className="flex flex-col items-center">
                    <span className={`grid h-6 w-6 place-items-center rounded-full ${i <= at ? 'bg-ink text-surface' : 'border border-line'}`}>{i <= at && <CircleCheck size={14} aria-hidden />}</span>
                    {i < order.length - 1 && <span className={`min-h-6 w-px flex-1 ${i < at ? 'bg-ink' : 'bg-line'}`} />}
                  </span>
                  <span className={`pb-5 text-sm font-medium ${i <= at ? '' : 'text-muted'}`}>{t(`req.status.${k}`)}</span>
                </li>
              ))}
            </ol>
          )}
        {data.reply && <div className="rounded-2xl bg-wash p-5"><p className="text-xs font-medium uppercase tracking-wider text-muted">{t('req.reply')}</p><p className="mt-1.5">{data.reply}</p></div>}
        <dl className="divide-y divide-line rounded-2xl border border-line text-sm">
          {([
            [t('req.route'), `${data.origin} → ${data.destination}`],
            [t('req.material'), `${data.material}${data.weight_tonnes ? ` · ${data.weight_tonnes} t` : ''}`],
            [t('req.pickupOn'), data.planned_start ? new Date(data.planned_start).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : data.pickup_date],
            ...(data.quote_amount !== null ? [[t('req.quote'), `₹${data.quote_amount.toLocaleString('en-IN')}`]] : []),
          ] as [string, string][]).map(([k, v]) => (
            <div key={k} className="flex justify-between gap-6 px-5 py-3.5"><dt className="text-muted">{k}</dt><dd className="text-right font-medium">{v}</dd></div>
          ))}
        </dl>
      </div>
    </PublicFrame>
  )
}
