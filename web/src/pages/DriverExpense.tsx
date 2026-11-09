import { Ban, Camera, Check, CircleCheck, Clock, Ellipsis, Fuel, Package, Receipt, Utensils, Wallet, Wrench, X, type LucideIcon } from 'lucide-react'
import { useRef, useState, type FormEvent } from 'react'
import DriverShell from '../components/DriverShell'
import { type Trip } from '../lib/api'
import { useAuth } from '../lib/auth'
import { compressPhoto } from '../lib/capture/compress'
import { useI18n } from '../lib/i18n'
import { useLive } from '../lib/live'
import { useCachedApi } from '../lib/offline/cache'
import { newId } from '../lib/offline/db'
import { enqueueAction, flushOutbox, useOutbox } from '../lib/offline/outbox'

type Cat = 'fuel' | 'toll' | 'repair' | 'loading' | 'food' | 'fine' | 'other'
const CATS: [Cat, LucideIcon][] = [['fuel', Fuel], ['toll', Receipt], ['repair', Wrench], ['loading', Package], ['food', Utensils], ['fine', Ban], ['other', Ellipsis]]
interface Money { advances: number; approved: number; waiting: number; balance: number; recent_advances: { amount: number; note: string | null; given_at: string }[] }
interface Mine { id: string; category: Cat; amount: number; status: 'pending' | 'approved' | 'rejected'; review_note: string | null; trip_code: string | null }

const T = {
  en: { title: 'Add expense', cat: { fuel: 'Diesel', toll: 'Toll', repair: 'Repair', loading: 'Loading', food: 'Food', fine: 'Fine', other: 'Other' }, amount: 'Amount (₹)', litres: 'Litres', odo: 'Odometer (km)', note: 'Note (optional)', photo: 'Bill photo (optional)', retakePhoto: 'Photo added', save: 'Save', saving: 'Saving…', saved: 'Saved. The office will check it.', savedOffline: 'Saved on your phone. It is sent when the network returns.', another: 'Add another', noTrip: 'You have no trip to add an expense to.', recent: 'Your expenses', pending: 'Waiting', approved: 'Approved', rejected: 'Rejected', fuelNeeds: 'Diesel needs litres and the odometer reading.', cash: 'Cash with you', owed: 'Office owes you', clear: 'All settled', taken: 'Advance taken', okd: 'Approved', wait: 'Waiting', lastAdv: 'Last advance' },
  hi: { title: 'खर्चा जोड़ें', cat: { fuel: 'डीज़ल', toll: 'टोल', repair: 'मरम्मत', loading: 'लोडिंग', food: 'खाना', fine: 'जुर्माना', other: 'अन्य' }, amount: 'रकम (₹)', litres: 'लीटर', odo: 'ओडोमीटर (किमी)', note: 'नोट (वैकल्पिक)', photo: 'बिल का फोटो (वैकल्पिक)', retakePhoto: 'फोटो जुड़ गया', save: 'सेव करें', saving: 'सेव हो रहा है…', saved: 'सेव हो गया। दफ़्तर इसे जाँचेगा।', savedOffline: 'फ़ोन में सेव हो गया। नेटवर्क आते ही भेज दिया जाएगा।', another: 'एक और जोड़ें', noTrip: 'खर्चा जोड़ने के लिए आपकी कोई ट्रिप नहीं है।', recent: 'आपके खर्चे', pending: 'इंतज़ार में', approved: 'मंज़ूर', rejected: 'अस्वीकृत', fuelNeeds: 'डीज़ल के लिए लीटर और ओडोमीटर चाहिए।', cash: 'आपके पास कैश', owed: 'दफ़्तर से आपको मिलना है', clear: 'हिसाब बराबर', taken: 'एडवांस लिया', okd: 'मंज़ूर', wait: 'इंतज़ार में', lastAdv: 'पिछला एडवांस' },
  mr: { title: 'खर्च जोडा', cat: { fuel: 'डिझेल', toll: 'टोल', repair: 'दुरुस्ती', loading: 'लोडिंग', food: 'जेवण', fine: 'दंड', other: 'इतर' }, amount: 'रक्कम (₹)', litres: 'लिटर', odo: 'ओडोमीटर (किमी)', note: 'टीप (ऐच्छिक)', photo: 'बिलाचा फोटो (ऐच्छिक)', retakePhoto: 'फोटो जोडला', save: 'सेव्ह करा', saving: 'सेव्ह होत आहे…', saved: 'सेव्ह झाले. कार्यालय हे तपासेल.', savedOffline: 'फोनमध्ये सेव्ह झाले. नेटवर्क येताच पाठवले जाईल.', another: 'आणखी एक जोडा', noTrip: 'खर्च जोडण्यासाठी तुमची कोणतीही ट्रिप नाही.', recent: 'तुमचे खर्च', pending: 'प्रतीक्षेत', approved: 'मंजूर', rejected: 'नाकारले', fuelNeeds: 'डिझेलसाठी लिटर आणि ओडोमीटर हवे.', cash: 'तुमच्याकडे रोख', owed: 'कार्यालयाकडून तुम्हाला मिळायचे', clear: 'हिशोब बरोबर', taken: 'ॲडव्हान्स घेतला', okd: 'मंजूर', wait: 'प्रतीक्षेत', lastAdv: 'मागील ॲडव्हान्स' },
} as const

/** Driver screen: pick what it was (icons), type the amount, optionally add the bill photo. The entry is saved on the phone first, so it
 *  works with no network; the same id is used on every retry, so the office never sees it twice. */
export default function DriverExpense() {
  const { user } = useAuth()
  const { lang } = useI18n()
  const tx = T[lang]
  const { data: trips, loaded } = useCachedApi<Trip[]>('/trips/mine', user?.id ?? 'anon')
  const { waiting } = useOutbox()
  const { data: mineData, reload } = useCachedApi<Mine[]>('/expenses/mine', user?.id ?? 'anon', waiting) // reload when saved entries have been sent
  const mine = mineData ?? []
  const { data: money, reload: reloadMoney } = useCachedApi<Money>('/finance/mine', user?.id ?? 'anon', waiting) // nothing on a hired driver's link: it shows one trip only
  useLive(['expenses'], () => { reload(); reloadMoney() })
  const trip = trips ? trips.find((t) => t.state === 'in_transit') ?? trips.find((t) => t.state === 'planned') ?? trips.find((t) => t.state !== 'cancelled') ?? null : undefined
  const [cat, setCat] = useState<Cat>('fuel')
  const [f, setF] = useState({ amount: '', litres: '', odo: '', note: '' })
  const [photo, setPhoto] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<'sent' | 'phone' | null>(null)
  const entryId = useRef(newId())

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!trip) return
    setError(null)
    if (cat === 'fuel' && (!f.litres || !f.odo)) return setError(tx.fuelNeeds)
    setBusy(true)
    const data: Record<string, string> = { trip_id: trip.id, category: cat, amount: f.amount, incurred_at: new Date().toISOString() }
    if (cat === 'fuel') { data.litres = f.litres; data.odometer_km = f.odo }
    if (f.note.trim()) data.note = f.note.trim()
    const blob = photo ? await compressPhoto(photo) : undefined
    await enqueueAction('expense', data, blob, entryId.current) // safe on the phone before any network is tried
    await flushOutbox().catch(() => undefined)
    setDone(navigator.onLine ? 'sent' : 'phone')
    entryId.current = newId()
    setF({ amount: '', litres: '', odo: '', note: '' })
    setPhoto(null)
    reload()
    setBusy(false)
  }

  const big = 'h-16 w-full rounded-2xl border border-line bg-surface px-4 text-center text-2xl outline-none focus:border-ink'
  const num = (k: keyof typeof f) => ({ value: f[k], inputMode: 'decimal' as const, onChange: (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value.replace(/[^\d.]/g, '') }) })
  const statusChip = { pending: ['bg-wash text-muted', Clock, tx.pending], approved: ['bg-ok-soft text-ok', CircleCheck, tx.approved], rejected: ['bg-bad-soft text-bad', X, tx.rejected] } as const

  return (
    <DriverShell title={tx.title}>
      {money && (money.advances > 0 || money.approved > 0 || money.waiting > 0) && (
        <section aria-label={tx.cash} className="mb-6 rounded-3xl border border-line p-5">
          <p className="flex items-center gap-2 text-base text-muted"><Wallet size={20} aria-hidden /> {money.balance > 0 ? tx.cash : money.balance < 0 ? tx.owed : tx.clear}</p>
          {money.balance !== 0 && <p className="mt-1 text-4xl font-semibold tracking-tight tabular-nums">₹{Math.abs(money.balance).toLocaleString('en-IN')}</p>}
          <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
            {([[tx.taken, money.advances], [tx.okd, money.approved], [tx.wait, money.waiting]] as const).map(([k, v]) => (
              <div key={k} className="rounded-2xl bg-wash px-1 py-3"><dt className="text-xs text-muted">{k}</dt><dd className="mt-0.5 text-lg font-semibold tabular-nums">₹{v.toLocaleString('en-IN')}</dd></div>
            ))}
          </dl>
          {money.recent_advances[0] && (
            <p className="mt-3 text-sm text-muted">{tx.lastAdv}: ₹{money.recent_advances[0].amount.toLocaleString('en-IN')} · {new Date(money.recent_advances[0].given_at).toLocaleDateString(lang === 'en' ? 'en-IN' : lang === 'hi' ? 'hi-IN' : 'mr-IN', { day: 'numeric', month: 'short' })}{money.recent_advances[0].note ? ` · ${money.recent_advances[0].note}` : ''}</p>
          )}
        </section>
      )}
      {loaded && trip === null && <p className="rounded-2xl bg-wash p-4 text-lg text-muted">{tx.noTrip}</p>}
      {done ? (
        <div className="grid place-items-center gap-5 py-8 text-center">
          <span className="grid h-28 w-28 place-items-center rounded-full bg-ok-soft text-ok"><Check size={64} aria-hidden /></span>
          <p className="text-xl font-semibold" role="status">{done === 'sent' ? tx.saved : tx.savedOffline}</p>
          <button onClick={() => setDone(null)} className="h-16 w-full rounded-2xl bg-ink text-xl font-semibold text-surface">{tx.another}</button>
        </div>
      ) : trip && (
        <form onSubmit={(e) => void submit(e)} className="space-y-5">
          <p className="text-base text-muted">{trip.trip_code} · {trip.destination}</p>
          <div className="grid grid-cols-4 gap-2" role="radiogroup" aria-label={tx.title}>
            {CATS.map(([c, Icon]) => (
              <button type="button" key={c} role="radio" aria-checked={cat === c} onClick={() => setCat(c)}
                className={`flex min-h-20 flex-col items-center justify-center gap-1.5 rounded-2xl border px-1 py-3 text-sm ${cat === c ? 'border-ink bg-ink font-semibold text-surface' : 'border-line text-muted'}`}>
                <Icon size={28} aria-hidden /> {tx.cat[c]}
              </button>
            ))}
          </div>
          <input className={big} required aria-label={tx.amount} placeholder={tx.amount} {...num('amount')} />
          {cat === 'fuel' && (
            <div className="grid grid-cols-2 gap-3">
              <input className={`${big} !text-xl`} aria-label={tx.litres} placeholder={tx.litres} {...num('litres')} />
              <input className={`${big} !text-xl`} aria-label={tx.odo} placeholder={tx.odo} inputMode="numeric" value={f.odo} onChange={(e) => setF({ ...f, odo: e.target.value.replace(/\D/g, '') })} />
            </div>
          )}
          <input className="h-14 w-full rounded-2xl border border-line bg-surface px-4 text-lg outline-none focus:border-ink" aria-label={tx.note} placeholder={tx.note} maxLength={200} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
          <label className={`flex h-16 cursor-pointer items-center justify-center gap-2 rounded-2xl border border-dashed text-lg ${photo ? 'border-ok text-ok' : 'border-line text-muted'}`}>
            <Camera size={24} aria-hidden /> {photo ? tx.retakePhoto : tx.photo}
            <input type="file" accept="image/*" capture="environment" className="sr-only" aria-label={tx.photo} onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
          </label>
          {error && <p role="alert" className="text-center text-base font-medium text-bad">{error}</p>}
          <button disabled={busy} className="flex h-16 w-full items-center justify-center gap-2 rounded-2xl bg-ink text-xl font-semibold text-surface disabled:opacity-60"><Check size={26} aria-hidden /> {busy ? tx.saving : tx.save}</button>
        </form>
      )}

      {mine.length > 0 && (
        <section className="mt-10 space-y-3">
          <h2 className="text-base font-semibold text-muted">{tx.recent}</h2>
          <ul className="space-y-2.5">
            {mine.slice(0, 8).map((m) => {
              const [cls, Icon, label] = statusChip[m.status]
              return (
                <li key={m.id} className="rounded-2xl border border-line px-4 py-3.5">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-lg font-semibold">{tx.cat[m.category]} · ₹{m.amount.toLocaleString('en-IN')}</span>
                    <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-sm font-medium ${cls}`}><Icon size={16} aria-hidden /> {label}</span>
                  </div>
                  {m.status === 'rejected' && m.review_note && <p className="mt-1 text-base text-bad">{m.review_note}</p>}
                </li>
              )
            })}
          </ul>
        </section>
      )}
    </DriverShell>
  )
}
