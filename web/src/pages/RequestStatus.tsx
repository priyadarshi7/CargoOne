import { CircleCheck, CircleX, Clock, Truck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { BASE } from '../lib/api'
import { useI18n, type Lang } from '../lib/i18n'
import { PublicFrame } from './RequestTransport'

interface Status {
  reference: string; status: 'new' | 'accepted' | 'booked' | 'declined'; company_name: string; origin: string; destination: string; material: string
  weight_tonnes: number | null; pickup_date: string; reply: string | null; quote_amount: number | null; trip_code: string | null; planned_start: string | null; language: Lang
}
const ICON = { new: Clock, accepted: CircleCheck, booked: Truck, declined: CircleX } as const
const TONE = { new: 'text-warn', accepted: 'text-ok', booked: 'text-ok', declined: 'text-bad' } as const

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
  const Icon = ICON[data.status]
  return (
    <PublicFrame>
      <div className="space-y-5">
        <div className="flex items-center gap-3"><Icon size={40} className={TONE[data.status]} aria-hidden />
          <div><p className="text-sm text-muted">{t('req.reference')} <b className="tabular-nums text-ink">{data.reference}</b></p>
            <h1 role="status" className={`text-xl font-semibold ${TONE[data.status]}`}>{t(`req.st.${data.status}`, { trip: data.trip_code ?? '' })}</h1></div></div>
        {data.reply && <div className="rounded-xl bg-wash p-4"><p className="text-xs text-muted">{t('req.reply')}</p><p>{data.reply}</p></div>}
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
          <dt className="text-muted">{t('req.route')}</dt><dd className="font-medium">{data.origin} → {data.destination}</dd>
          <dt className="text-muted">{t('req.material')}</dt><dd className="font-medium">{data.material}{data.weight_tonnes ? ` · ${data.weight_tonnes} t` : ''}</dd>
          <dt className="text-muted">{t('req.pickupOn')}</dt><dd className="font-medium">{data.planned_start ? new Date(data.planned_start).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : data.pickup_date}</dd>
          {data.quote_amount !== null && <><dt className="text-muted">{t('req.quote')}</dt><dd className="font-medium tabular-nums">₹{data.quote_amount.toLocaleString('en-IN')}</dd></>}
        </dl>
      </div>
    </PublicFrame>
  )
}
