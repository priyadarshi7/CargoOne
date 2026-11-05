import { ArrowLeft, Ban, Check, CircleCheck, Clock, Ellipsis, Fuel, Package, Receipt, Utensils, Wrench, X, Camera, type LucideIcon } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, BASE, tokenStore, type Trip } from '../lib/api'
import { useAuth } from '../lib/auth'
import { compressPhoto } from '../lib/capture/compress'

type Cat = 'fuel' | 'toll' | 'repair' | 'loading' | 'food' | 'fine' | 'other'
const CATS: [Cat, LucideIcon][] = [['fuel', Fuel], ['toll', Receipt], ['repair', Wrench], ['loading', Package], ['food', Utensils], ['fine', Ban], ['other', Ellipsis]]
interface Mine { id: string; category: Cat; amount: number; status: 'pending' | 'approved' | 'rejected'; review_note: string | null; trip_code: string | null }

const T = {
  en: { title: 'Add expense', cat: { fuel: 'Diesel', toll: 'Toll', repair: 'Repair', loading: 'Loading', food: 'Food', fine: 'Fine', other: 'Other' }, amount: 'Amount (₹)', litres: 'Litres', odo: 'Odometer (km)', note: 'Note (optional)', photo: 'Bill photo (optional)', retakePhoto: 'Photo added', save: 'Save', saving: 'Saving…', saved: 'Saved. The office will check it.', another: 'Add another', noTrip: 'You have no trip to add an expense to.', recent: 'Your expenses', pending: 'Waiting', approved: 'Approved', rejected: 'Rejected', fail: 'Could not save. Check the network and try again.', fuelNeeds: 'Diesel needs litres and the odometer reading.' },
  hi: { title: 'खर्चा जोड़ें', cat: { fuel: 'डीज़ल', toll: 'टोल', repair: 'मरम्मत', loading: 'लोडिंग', food: 'खाना', fine: 'जुर्माना', other: 'अन्य' }, amount: 'रकम (₹)', litres: 'लीटर', odo: 'ओडोमीटर (किमी)', note: 'नोट (वैकल्पिक)', photo: 'बिल का फोटो (वैकल्पिक)', retakePhoto: 'फोटो जुड़ गया', save: 'सेव करें', saving: 'सेव हो रहा है…', saved: 'सेव हो गया। दफ़्तर इसे जाँचेगा।', another: 'एक और जोड़ें', noTrip: 'खर्चा जोड़ने के लिए आपकी कोई ट्रिप नहीं है।', recent: 'आपके खर्चे', pending: 'इंतज़ार में', approved: 'मंज़ूर', rejected: 'अस्वीकृत', fail: 'सेव नहीं हो सका। नेटवर्क देखकर दोबारा कोशिश करें।', fuelNeeds: 'डीज़ल के लिए लीटर और ओडोमीटर चाहिए।' },
  mr: { title: 'खर्च जोडा', cat: { fuel: 'डिझेल', toll: 'टोल', repair: 'दुरुस्ती', loading: 'लोडिंग', food: 'जेवण', fine: 'दंड', other: 'इतर' }, amount: 'रक्कम (₹)', litres: 'लिटर', odo: 'ओडोमीटर (किमी)', note: 'टीप (ऐच्छिक)', photo: 'बिलाचा फोटो (ऐच्छिक)', retakePhoto: 'फोटो जोडला', save: 'सेव्ह करा', saving: 'सेव्ह होत आहे…', saved: 'सेव्ह झाले. कार्यालय हे तपासेल.', another: 'आणखी एक जोडा', noTrip: 'खर्च जोडण्यासाठी तुमची कोणतीही ट्रिप नाही.', recent: 'तुमचे खर्च', pending: 'प्रतीक्षेत', approved: 'मंजूर', rejected: 'नाकारले', fail: 'सेव्ह होऊ शकले नाही. नेटवर्क तपासून पुन्हा प्रयत्न करा.', fuelNeeds: 'डिझेलसाठी लिटर आणि ओडोमीटर हवे.' },
} as const

/** Driver screen: pick what it was (icons), type the amount, optionally add the bill photo. Online only for now. */
export default function DriverExpense() {
  const { user } = useAuth()
  const tx = T[user?.language ?? 'en']
  const [trip, setTrip] = useState<Trip | null | undefined>(undefined)
  const [mine, setMine] = useState<Mine[]>([])
  const [cat, setCat] = useState<Cat>('fuel')
  const [f, setF] = useState({ amount: '', litres: '', odo: '', note: '' })
  const [photo, setPhoto] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const entryId = useRef(crypto.randomUUID().replaceAll('-', '')) // same id on every retry: the server never saves it twice

  const loadMine = () => api<Mine[]>('/expenses/mine').then(setMine).catch(() => undefined)
  useEffect(() => {
    api<Trip[]>('/trips/mine').then((all) => setTrip(all.find((t) => t.state === 'in_transit') ?? all.find((t) => t.state === 'planned') ?? all.find((t) => t.state !== 'cancelled') ?? null)).catch(() => setTrip(null))
    void loadMine()
  }, [])

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!trip) return
    setError(null)
    if (cat === 'fuel' && (!f.litres || !f.odo)) return setError(tx.fuelNeeds)
    setBusy(true)
    try {
      const form = new FormData()
      form.set('client_expense_id', entryId.current)
      form.set('trip_id', trip.id)
      form.set('category', cat)
      form.set('amount', f.amount)
      form.set('incurred_at', new Date().toISOString())
      if (cat === 'fuel') { form.set('litres', f.litres); form.set('odometer_km', f.odo) }
      if (f.note.trim()) form.set('note', f.note.trim())
      if (photo) form.set('photo', await compressPhoto(photo), 'bill.webp')
      const token = tokenStore.get()
      const res = await fetch(`${BASE}/expenses`, { method: 'POST', body: form, headers: token ? { Authorization: `Bearer ${token}` } : {} })
      if (!res.ok) {
        const detail = await res.json().then((j) => j.detail).catch(() => null)
        throw new ApiError(res.status, typeof detail === 'string' ? detail : tx.fail)
      }
      setDone(true)
      entryId.current = crypto.randomUUID().replaceAll('-', '')
      setF({ amount: '', litres: '', odo: '', note: '' })
      setPhoto(null)
      void loadMine()
    } catch (err) {
      setError(err instanceof ApiError && err.status < 500 ? err.message : tx.fail)
    } finally {
      setBusy(false)
    }
  }

  const big = 'w-full rounded-2xl border border-line px-4 py-4 text-center text-2xl outline-none focus:border-accent'
  const num = (k: keyof typeof f) => ({ value: f[k], inputMode: 'decimal' as const, onChange: (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value.replace(/[^\d.]/g, '') }) })
  const statusChip = { pending: ['bg-wash text-muted', Clock, tx.pending], approved: ['bg-ok-soft text-ok', CircleCheck, tx.approved], rejected: ['bg-bad-soft text-bad', X, tx.rejected] } as const

  return (
    <div className="mx-auto min-h-full max-w-md px-5 pb-10 pt-6">
      <header className="mb-5 flex items-center gap-3">
        <Link to="/driver" aria-label="Back" className="grid h-12 w-12 place-items-center rounded-full bg-wash text-ink"><ArrowLeft aria-hidden /></Link>
        <h1 className="text-xl font-semibold">{tx.title}</h1>
      </header>

      {trip === null && <p className="rounded-2xl bg-wash p-4 text-muted">{tx.noTrip}</p>}
      {done ? (
        <div className="grid place-items-center gap-5 py-10 text-center">
          <span className="grid h-28 w-28 place-items-center rounded-full bg-ok-soft text-ok"><Check size={64} aria-hidden /></span>
          <p className="text-lg font-semibold" role="status">{tx.saved}</p>
          <button onClick={() => setDone(false)} className="rounded-2xl bg-ink px-8 py-4 text-lg font-semibold text-surface">{tx.another}</button>
        </div>
      ) : trip && (
        <form onSubmit={submit} className="space-y-5">
          <p className="text-sm text-muted">{trip.trip_code} · {trip.destination}</p>
          <div className="grid grid-cols-4 gap-2" role="radiogroup" aria-label={tx.title}>
            {CATS.map(([c, Icon]) => (
              <button type="button" key={c} role="radio" aria-checked={cat === c} onClick={() => setCat(c)}
                className={`flex flex-col items-center gap-1.5 rounded-2xl border px-1 py-3 text-xs ${cat === c ? 'border-accent bg-accent-soft font-semibold text-accent' : 'border-line text-muted'}`}>
                <Icon size={26} aria-hidden /> {tx.cat[c]}
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
          <input className="w-full rounded-2xl border border-line px-4 py-3 outline-none focus:border-accent" aria-label={tx.note} placeholder={tx.note} maxLength={200} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
          <label className={`flex cursor-pointer items-center justify-center gap-2 rounded-2xl border border-dashed px-4 py-4 ${photo ? 'border-ok text-ok' : 'border-line text-muted'}`}>
            <Camera aria-hidden /> {photo ? tx.retakePhoto : tx.photo}
            <input type="file" accept="image/*" capture="environment" className="sr-only" aria-label={tx.photo} onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
          </label>
          {error && <p role="alert" className="text-center text-sm font-medium text-bad">{error}</p>}
          <button disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-2xl bg-ink py-4 text-lg font-semibold text-surface disabled:opacity-60"><Check aria-hidden /> {busy ? tx.saving : tx.save}</button>
        </form>
      )}

      {mine.length > 0 && (
        <section className="mt-10 space-y-3">
          <h2 className="font-semibold">{tx.recent}</h2>
          <ul className="space-y-2">
            {mine.slice(0, 8).map((m) => {
              const [cls, Icon, label] = statusChip[m.status]
              return (
                <li key={m.id} className="rounded-2xl border border-line px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium">{tx.cat[m.category]} · ₹{m.amount.toLocaleString('en-IN')}</span>
                    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${cls}`}><Icon size={14} aria-hidden /> {label}</span>
                  </div>
                  {m.status === 'rejected' && m.review_note && <p className="mt-1 text-sm text-bad">{m.review_note}</p>}
                </li>
              )
            })}
          </ul>
        </section>
      )}
    </div>
  )
}
