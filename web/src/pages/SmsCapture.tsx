import { CircleCheck, Clock, LinkIcon, LoaderCircle } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { CaptureFlow } from '../components/CaptureFlow'
import { BASE, type User } from '../lib/api'

interface Info { destination: string; vehicle: string; status: string; retakes_left: number }
type State = { kind: 'loading' } | { kind: 'ok'; info: Info } | { kind: 'gone' } | { kind: 'unknown' } | { kind: 'error' }

/** Public page opened from an SMS link: no app, no login, one trip. The link itself is the credential. */
export default function SmsCapture() {
  const { token = '' } = useParams()
  const [params] = useSearchParams()
  const lang = (['hi', 'mr', 'en'].includes(params.get('l') ?? '') ? params.get('l') : 'hi') as User['language']
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    fetch(`${BASE}/u/${encodeURIComponent(token)}`)
      .then(async (r) => {
        if (r.ok) return setState({ kind: 'ok', info: (await r.json()) as Info })
        setState({ kind: r.status === 410 ? 'gone' : r.status === 404 ? 'unknown' : 'error' })
      })
      .catch(() => setState({ kind: 'error' })) // offline when opening the link: nothing to show yet
  }, [token])

  if (state.kind === 'loading') return <Center tone="bg-surface"><LoaderCircle size={96} className="animate-spin text-accent" aria-label="Loading" /></Center>
  if (state.kind === 'gone') return <Center tone="bg-warn-soft text-warn"><Clock size={140} aria-label="Link expired" /><p className="text-center text-xl font-semibold">{TEXT[lang].gone}</p></Center>
  if (state.kind === 'unknown') return <Center tone="bg-bad-soft text-bad"><LinkIcon size={140} aria-label="Link not valid" /><p className="text-center text-xl font-semibold">{TEXT[lang].unknown}</p></Center>
  if (state.kind === 'error') return <Center tone="bg-accent-soft text-accent"><LinkIcon size={140} aria-label="Cannot open link" /><p className="text-center text-xl font-semibold">{TEXT[lang].error}</p></Center>

  const { info } = state
  if (!['pending', 'retake_requested', 'uploaded'].includes(info.status)) {
    return <Center tone="bg-ok-soft text-ok"><CircleCheck size={160} aria-label="Already done" /><p className="text-center text-xl font-semibold">{TEXT[lang].done}</p></Center>
  }
  return <CaptureFlow tripId="" linkToken={token} destination={info.destination} lang={lang} />
}

const TEXT: Record<User['language'], Record<'gone' | 'unknown' | 'error' | 'done', string>> = {
  hi: { gone: 'यह लिंक पुराना हो गया है। दफ़्तर से नया लिंक मंगवाइए।', unknown: 'यह लिंक सही नहीं है।', error: 'लिंक नहीं खुल रहा। नेटवर्क देखकर दोबारा कोशिश कीजिए।', done: 'रसीद मिल चुकी है। धन्यवाद।' },
  mr: { gone: 'ही लिंक जुनी झाली आहे. कार्यालयातून नवीन लिंक मागवा.', unknown: 'ही लिंक बरोबर नाही.', error: 'लिंक उघडत नाही. नेटवर्क तपासून पुन्हा प्रयत्न करा.', done: 'पावती मिळाली आहे. धन्यवाद.' },
  en: { gone: 'This link has expired. Ask the office for a new one.', unknown: 'This link is not valid.', error: 'Cannot open the link. Check the network and try again.', done: 'Receipt already received. Thank you.' },
}

function Center({ tone, children }: { tone: string; children: ReactNode }) {
  return <div className={`grid min-h-full place-items-center px-6 ${tone}`}><div className="flex max-w-sm flex-col items-center gap-8">{children}</div></div>
}
