import { Clock, LinkIcon, LoaderCircle } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Navigate, Route, Routes, useParams, useSearchParams } from 'react-router-dom'
import { api, ApiError, BASE, linkStore, setActiveLink, type User } from '../lib/api'
import { LinkAuthProvider } from '../lib/auth'
import { DriverBaseProvider } from '../lib/driverBase'
import { useI18n } from '../lib/i18n'
import Capture from './Capture'
import DriverExpense from './DriverExpense'
import DriverHelp from './DriverHelp'
import DriverHome from './DriverHome'
import DriverMessages from './DriverMessages'

type Lang = User['language']
type State = { kind: 'loading' } | { kind: 'ok'; user: User } | { kind: 'gone' } | { kind: 'unknown' } | { kind: 'error' }

const TEXT: Record<Lang, Record<'gone' | 'unknown' | 'error', string>> = {
  hi: { gone: 'यह लिंक पुराना हो गया है। दफ़्तर से नया लिंक मंगवाइए।', unknown: 'यह लिंक सही नहीं है।', error: 'लिंक नहीं खुल रहा। नेटवर्क देखकर दोबारा कोशिश कीजिए।' },
  mr: { gone: 'ही लिंक जुनी झाली आहे. कार्यालयातून नवीन लिंक मागवा.', unknown: 'ही लिंक बरोबर नाही.', error: 'लिंक उघडत नाही. नेटवर्क तपासून पुन्हा प्रयत्न करा.' },
  en: { gone: 'This link has expired. Ask the office for a new one.', unknown: 'This link is not valid.', error: 'Cannot open the link. Check the network and try again.' },
}

const profileKey = (token: string) => `cargoone.linkuser.${token.slice(0, 16)}`
const savedProfile = (token: string): User | null => { try { return JSON.parse(localStorage.getItem(profileKey(token)) ?? 'null') as User | null } catch { return null } }
const saveProfile = (token: string, u: User) => { try { localStorage.setItem(profileKey(token), JSON.stringify(u)) } catch { /* storage blocked: the next offline start asks for the network */ } }

/** A hired driver's private link. There is no app to install and no sign-in: the link is the credential, and behind it is the same driver app
 *  an own driver uses (home, messages, expenses, help, the photo screen), for this one trip. It is installable, keeps working with no network,
 *  and can receive alerts. The first open needs the network; after that the phone's saved copy is enough. */
export default function LinkApp() {
  const { token = '' } = useParams()
  const [params] = useSearchParams()
  const { lang, setLang } = useI18n()
  const [state, setState] = useState<State>({ kind: 'loading' })
  const asked = (['hi', 'mr', 'en'].includes(params.get('l') ?? '') ? params.get('l') : 'hi') as Lang

  useEffect(() => {
    setActiveLink(token) // every request this page makes carries the link
    linkStore.set(token)
    let alive = true
    void (async () => {
      try {
        const me = await api<User>('/auth/me')
        saveProfile(token, me)
        if (alive) setState({ kind: 'ok', user: me })
      } catch (e) {
        if (!alive) return
        if (e instanceof ApiError) { // the server answered: say whether the link is old or never existed
          const why = await fetch(`${BASE}/u/${encodeURIComponent(token)}`).then((r) => r.status).catch(() => 0)
          if (why === 410 || why === 404 || e.status === 401) linkStore.clear()
          setState({ kind: why === 404 ? 'unknown' : 'gone' })
          return
        }
        const user = savedProfile(token) // no network: the phone still knows who this link is for
        setState(user ? { kind: 'ok', user } : { kind: 'error' })
      }
    })()
    return () => { alive = false; setActiveLink(null) }
  }, [token])

  useEffect(() => { // the office chose a language when it made the link; the driver's own choice, once made, wins
    try { if (!localStorage.getItem('cargoone.lang')) setLang(asked) } catch { /* storage blocked: stays as it is */ }
  }, [asked, setLang])

  const text = TEXT[lang]
  if (state.kind === 'loading') return <Center tone="bg-surface"><LoaderCircle size={96} className="animate-spin text-accent" aria-label="Loading" /></Center>
  if (state.kind === 'gone') return <Center tone="bg-warn-soft text-warn"><Clock size={140} aria-label="Link expired" /><p className="text-center text-xl font-semibold">{text.gone}</p></Center>
  if (state.kind === 'unknown') return <Center tone="bg-bad-soft text-bad"><LinkIcon size={140} aria-label="Link not valid" /><p className="text-center text-xl font-semibold">{text.unknown}</p></Center>
  if (state.kind === 'error') return <Center tone="bg-accent-soft text-accent"><LinkIcon size={140} aria-label="Cannot open link" /><p className="text-center text-xl font-semibold">{text.error}</p></Center>

  return (
    <LinkAuthProvider user={state.user}>
      <DriverBaseProvider link={token}>
        <Routes>
          <Route index element={<DriverHome />} />
          <Route path="messages" element={<DriverMessages />} />
          <Route path="help" element={<DriverHelp />} />
          <Route path="expense" element={<DriverExpense />} />
          <Route path="trip/:id" element={<Capture />} />
          <Route path="*" element={<Navigate to="" replace />} />
        </Routes>
      </DriverBaseProvider>
    </LinkAuthProvider>
  )
}

function Center({ tone, children }: { tone: string; children: ReactNode }) {
  return <div className={`grid min-h-full place-items-center px-6 ${tone}`}><div className="flex max-w-sm flex-col items-center gap-8">{children}</div></div>
}
