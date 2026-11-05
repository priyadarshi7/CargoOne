import { CircleCheck, KeyRound } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, ApiError, BASE, tokenStore, type User } from '../lib/api'
import { useAuth } from '../lib/auth'

type Lang = 'en' | 'hi' | 'mr'
const TXT: Record<Lang, Record<'hello' | 'intro' | 'pin' | 'again' | 'save' | 'mismatch' | 'dead' | 'fail', string>> = {
  en: { hello: 'Welcome, {name}', intro: 'Choose a PIN of 4 to 8 digits. You will use it with your mobile number every time you sign in. Nobody else will see it.', pin: 'New PIN', again: 'Type it again', save: 'Save and open the app', mismatch: 'The two PINs are different.', dead: 'This link has already been used or has expired. Ask the office to send a new one.', fail: 'Could not save. Try again.' },
  hi: { hello: 'स्वागत है, {name}', intro: '4 से 8 अंकों का PIN चुनें। हर बार साइन इन करते समय यह आपके मोबाइल नंबर के साथ लगेगा। इसे कोई और नहीं देखेगा।', pin: 'नया PIN', again: 'फिर से लिखें', save: 'सेव करें और ऐप खोलें', mismatch: 'दोनों PIN अलग हैं।', dead: 'यह लिंक इस्तेमाल हो चुका है या ख़त्म हो गया है। दफ़्तर से नया लिंक माँगें।', fail: 'सेव नहीं हुआ। फिर कोशिश करें।' },
  mr: { hello: 'स्वागत, {name}', intro: '4 ते 8 अंकांचा PIN निवडा. प्रत्येक वेळी साइन इन करताना तो तुमच्या मोबाईल नंबरसोबत लागेल. तो इतर कोणालाही दिसणार नाही.', pin: 'नवीन PIN', again: 'पुन्हा लिहा', save: 'सेव्ह करा आणि अ‍ॅप उघडा', mismatch: 'दोन्ही PIN वेगळे आहेत.', dead: 'ही लिंक वापरून झाली आहे किंवा संपली आहे. कार्यालयाकडून नवीन लिंक मागा.', fail: 'सेव्ह झाले नाही. पुन्हा प्रयत्न करा.' },
}

/** The page a new driver opens from the WhatsApp message: pick a PIN once, then land signed in on the home screen. */
export default function Onboard() {
  const { token = '' } = useParams()
  const { adopt } = useAuth()
  const nav = useNavigate()
  const [info, setInfo] = useState<{ name: string; language: Lang } | 'dead' | null>(null)
  const [pin, setPin] = useState('')
  const [again, setAgain] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    fetch(`${BASE}/onboard/${encodeURIComponent(token)}`).then(async (r) => setInfo(r.ok ? await r.json() : 'dead')).catch(() => setInfo('dead'))
  }, [token])

  const lang: Lang = info && info !== 'dead' ? info.language : 'en'
  const x = TXT[lang]
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (pin !== again) return setError(x.mismatch)
    setBusy(true)
    setError(null)
    try {
      const res = await api<{ access_token: string; user: User }>(`/onboard/${encodeURIComponent(token)}`, { method: 'POST', body: JSON.stringify({ pin }) })
      tokenStore.set(res.access_token)
      adopt(res.access_token, res.user)
      nav('/driver', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 410 ? err.message : err instanceof ApiError ? x.dead : x.fail)
      setBusy(false)
    }
  }

  if (info === null) return <p className="p-8 text-center text-muted">…</p>
  if (info === 'dead') return <main className="mx-auto max-w-md p-8"><p role="alert" className="text-lg">{TXT.en.dead}</p><p className="mt-3 text-lg">{TXT.hi.dead}</p><p className="mt-3 text-lg">{TXT.mr.dead}</p></main>
  return (
    <main className="mx-auto flex min-h-full max-w-md flex-col gap-5 px-6 py-10">
      <CircleCheck size={56} className="text-ok" aria-hidden />
      <h1 className="text-3xl font-semibold tracking-tight">{x.hello.replace('{name}', info.name)}</h1>
      <p className="text-muted">{x.intro}</p>
      <form onSubmit={(e) => void submit(e)} className="space-y-4">
        <label className="block space-y-1"><span className="text-sm font-medium">{x.pin}</span>
          <input type="password" inputMode="numeric" autoComplete="new-password" required minLength={4} maxLength={8} pattern="\d{4,8}" value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
            className="w-full rounded-xl border border-line bg-surface px-4 py-4 text-center text-2xl tracking-[0.5em]" />
        </label>
        <label className="block space-y-1"><span className="text-sm font-medium">{x.again}</span>
          <input type="password" inputMode="numeric" autoComplete="new-password" required minLength={4} maxLength={8} pattern="\d{4,8}" value={again} onChange={(e) => setAgain(e.target.value.replace(/\D/g, ''))}
            className="w-full rounded-xl border border-line bg-surface px-4 py-4 text-center text-2xl tracking-[0.5em]" />
        </label>
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
        <button disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-xl bg-ink py-4 text-lg font-semibold text-surface disabled:opacity-60"><KeyRound aria-hidden /> {x.save}</button>
      </form>
    </main>
  )
}
