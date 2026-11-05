import { FileText, Phone } from 'lucide-react'
import { download, type DriverTrip } from '../lib/api'
import { useI18n } from '../lib/i18n'

/** Everything the driver needs to know about one trip before starting it: facts and the LR copy to print or show, no forms. */
export default function DriverTripDetails({ trip }: { trip: DriverTrip }) {
  const { t, lang } = useI18n()
  const start = trip.planned_start ? new Date(trip.planned_start).toLocaleString(lang === 'en' ? 'en-IN' : `${lang}-IN`, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : t('drv.tbd')
  const goods = [trip.material, trip.weight_tonnes ? `${trip.weight_tonnes} t` : null, trip.packages ? `${trip.packages} pkg` : null].filter(Boolean).join(' · ')
  const rows: [string, string | null][] = [
    [t('drv.lr'), trip.lr_no], [t('drv.truck'), trip.vehicle], [t('drv.startAt'), start], [t('drv.goods'), goods || null], [t('drv.ewb'), trip.eway_bill_no], [t('drv.deliverTo'), trip.consignee_name],
  ]
  return (
    <section aria-label={trip.trip_code} className="space-y-4 border-t border-line p-4">
      <dl className="grid grid-cols-[auto_1fr] gap-x-5 gap-y-3 text-base">
        {rows.filter(([, v]) => v).map(([k, v]) => (<div key={k} className="contents"><dt className="text-muted">{k}</dt><dd className="min-w-0 break-words font-semibold">{v}</dd></div>))}
      </dl>
      <div className="grid gap-3">
        {trip.consignee_phone && <a href={`tel:${trip.consignee_phone}`} className="flex h-14 items-center justify-center gap-2 rounded-xl border border-line text-lg font-medium"><Phone size={22} aria-hidden /> {t('drv.call')}</a>}
        <button onClick={() => void download(`/trips/${trip.id}/lr.pdf`, `${trip.trip_code}-LR.pdf`).catch(() => undefined)} className="flex h-14 items-center justify-center gap-2 rounded-xl border border-line text-lg font-medium"><FileText size={22} aria-hidden /> {t('drv.lrcopy')}</button>
      </div>
    </section>
  )
}
