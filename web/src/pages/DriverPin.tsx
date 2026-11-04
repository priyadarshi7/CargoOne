import { Check, KeyRound } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { api, ApiError, type User } from '../lib/api'
import { useAuth } from '../lib/auth'

const TEXT: Record<User['language'], Record<'title' | 'old' | 'new' | 'again' | 'save' | 'same' | 'hint' | 'wrong', string>> = {
  hi: { title: 'अपना नया पिन चुनिए', old: 'अभी का पिन', new: 'नया पिन', again: 'नया पिन दोबारा', save: 'सेव करें', same: 'दोनों पिन एक जैसे नहीं हैं।', hint: '4 से 8 अंक। 1234 या 1111 जैसा आसान पिन नहीं।', wrong: 'अभी का पिन सही नहीं है।' },
  mr: { title: 'तुमचा नवीन पिन निवडा', old: 'सध्याचा पिन', new: 'नवीन पिन', again: 'नवीन पिन पुन्हा', save: 'सेव्ह करा', same: 'दोन्ही पिन सारखे नाहीत.', hint: '4 ते 8 अंक. 1234 किंवा 1111 सारखा सोपा पिन नको.', wrong: 'सध्याचा पिन बरोबर नाही.' },
  en: { title: 'Choose your own PIN', old: 'Current PIN', new: 'New PIN', again: 'New PIN again', save: 'Save', same: 'The two PINs are not the same.', hint: '4 to 8 digits. Not an easy one like 1234 or 1111.', wrong: 'The current PIN is not correct.' },
}

/** Driver screen: after an office reset the temporary PIN must be replaced before anything else works. Also reachable
 *  voluntarily from the driver home. Digits only, big fields, the driver's own language. */
export default function DriverPin() {
  const { user, adopt } = useAuth()
  const nav = useNavigate()
  const [cur, setCur] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (!user) return <Navigate to="/login" replace />
  const tx = TEXT[user.language]

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (next !== again) return setError(tx.same)
    setBusy(true)
    try {
      const res = await api<{ access_token: string; user: User }>('/auth/change-secret', { method: 'POST', body: JSON.stringify({ current: cur, new: next }) })
      adopt(res.access_token, res.user)
      nav('/driver', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? (err.status === 403 ? tx.wrong : err.status === 422 ? tx.hint : err.message) : tx.hint)
    } finally {
      setBusy(false)
    }
  }

  const field = 'w-full rounded-2xl border border-line px-4 py-4 text-center text-2xl tracking-[0.4em] outline-none focus:border-accent'
  const digits = (set: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement>) => set(e.target.value.replace(/\D/g, '').slice(0, 8))
  return (
    <form onSubmit={submit} className="mx-auto flex min-h-full max-w-sm flex-col justify-center gap-5 px-6 py-10">
      <div className="flex flex-col items-center gap-3 text-center">
        <span className="grid h-20 w-20 place-items-center rounded-full bg-accent-soft text-accent"><KeyRound size={40} aria-hidden /></span>
        <h1 className="text-xl font-semibold">{tx.title}</h1>
      </div>
      <input className={field} inputMode="numeric" type="password" autoComplete="current-password" placeholder={tx.old} aria-label={tx.old} value={cur} onChange={digits(setCur)} required />
      <input className={field} inputMode="numeric" type="password" autoComplete="new-password" placeholder={tx.new} aria-label={tx.new} value={next} onChange={digits(setNext)} required />
      <input className={field} inputMode="numeric" type="password" autoComplete="new-password" placeholder={tx.again} aria-label={tx.again} value={again} onChange={digits(setAgain)} required />
      {!error && <p className="text-center text-sm text-muted">{tx.hint}</p>}
      {error && <p role="alert" className="text-center text-sm font-medium text-bad">{error}</p>}
      <button disabled={busy} className="flex items-center justify-center gap-2 rounded-2xl bg-accent py-4 text-lg font-semibold text-on-solid disabled:opacity-60">
        <Check aria-hidden /> {tx.save}
      </button>
    </form>
  )
}
