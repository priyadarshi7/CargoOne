import { FileText, Phone } from 'lucide-react'
import { download, type DriverTrip } from '../lib/api'
import { useAuth } from '../lib/auth'

const TXT = {
  en: { lr: 'LR number', route: 'Route', truck: 'Truck', start: 'Start', goods: 'Goods', consignee: 'Deliver to', ewb: 'E-way bill', pdf: 'LR copy (PDF)', call: 'Call', tbd: 'To be told' },
  hi: { lr: 'LR नंबर', route: 'रूट', truck: 'ट्रक', start: 'शुरू', goods: 'माल', consignee: 'किसको पहुँचाना है', ewb: 'ई-वे बिल', pdf: 'LR कॉपी (PDF)', call: 'फ़ोन करें', tbd: 'बाद में बताया जाएगा' },
  mr: { lr: 'LR क्रमांक', route: 'मार्ग', truck: 'ट्रक', start: 'सुरू', goods: 'माल', consignee: 'कोणाला पोहोचवायचे', ewb: 'ई-वे बिल', pdf: 'LR प्रत (PDF)', call: 'फोन करा', tbd: 'नंतर सांगितले जाईल' },
} as const

/** Everything the driver needs to know about one trip before starting it: no forms, just facts and the LR copy to print or show. */
export default function DriverTripDetails({ trip }: { trip: DriverTrip }) {
  const { user } = useAuth()
  const lang = user?.language ?? 'en'
  const x = TXT[lang]
  const start = trip.planned_start ? new Date(trip.planned_start).toLocaleString(lang === 'en' ? 'en-IN' : `${lang}-IN`, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : x.tbd
  const goods = [trip.material, trip.weight_tonnes ? `${trip.weight_tonnes} t` : null, trip.packages ? `${trip.packages} pkg` : null].filter(Boolean).join(' · ')
  const rows: [string, string | null][] = [[x.lr, trip.lr_no], [x.route, `${trip.origin} → ${trip.destination}`], [x.truck, trip.vehicle], [x.start, start], [x.goods, goods || null], [x.ewb, trip.eway_bill_no]]
  return (
    <section aria-label={trip.trip_code} className="mt-4 space-y-3 rounded-2xl border border-line p-4">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
        {rows.filter(([, v]) => v).map(([k, v]) => (<div key={k} className="contents"><dt className="text-muted">{k}</dt><dd className="min-w-0 break-words font-medium">{v}</dd></div>))}
        {trip.consignee_name && <><dt className="text-muted">{x.consignee}</dt><dd className="font-medium">{trip.consignee_name}</dd></>}
      </dl>
      <div className="flex flex-wrap gap-2">
        {trip.consignee_phone && <a href={`tel:${trip.consignee_phone}`} className="inline-flex items-center gap-1.5 rounded-xl border border-line px-4 py-2.5 text-sm font-medium"><Phone size={16} aria-hidden /> {x.call}</a>}
        <button onClick={() => void download(`/trips/${trip.id}/lr.pdf`, `${trip.trip_code}-LR.pdf`).catch(() => undefined)} className="inline-flex items-center gap-1.5 rounded-xl border border-line px-4 py-2.5 text-sm font-medium"><FileText size={16} aria-hidden /> {x.pdf}</button>
      </div>
    </section>
  )
}
