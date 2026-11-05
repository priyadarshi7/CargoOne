import { Camera, CircleCheck, CloudUpload, KeyRound, LogOut, MapPin, Play, Wallet } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import DriverInbox from '../components/DriverInbox'
import DriverTripDetails from '../components/DriverTripDetails'
import InstallBanner from '../components/InstallBanner'
import { statusIcon } from '../components/StatusBadge'
import { api, tokenStore, type DriverTrip, type PodStatus, type User } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useSyncedQueue } from '../lib/capture/sync'
import { useTracker } from '../lib/tracker'

const OPEN: PodStatus[] = ['pending', 'retake_requested']
const START: Record<'en' | 'hi' | 'mr', string> = { en: 'Start trip', hi: 'यात्रा शुरू करें', mr: 'प्रवास सुरू करा' }

const LOC: Record<'en' | 'hi' | 'mr', Record<'title' | 'body' | 'allow' | 'later' | 'on', string>> = {
  en: { title: 'Share your location during trips?', body: 'The office sees where your truck is, only while a trip is running. You can stop any time.', allow: 'Allow', later: 'Not now', on: 'Location on' },
  hi: { title: 'यात्रा के दौरान अपनी लोकेशन साझा करें?', body: 'दफ़्तर को सिर्फ़ यात्रा चलने के समय आपकी गाड़ी की जगह दिखेगी। आप कभी भी बंद कर सकते हैं।', allow: 'अनुमति दें', later: 'अभी नहीं', on: 'लोकेशन चालू' },
  mr: { title: 'प्रवासादरम्यान तुमचे लोकेशन शेअर करायचे?', body: 'कार्यालयाला फक्त प्रवास सुरू असताना तुमच्या गाडीची जागा दिसेल. तुम्ही केव्हाही बंद करू शकता.', allow: 'परवानगी द्या', later: 'आत्ता नाही', on: 'लोकेशन चालू' },
}

/** Driver surface: one primary action, icons over text, no forms. */
export default function DriverHome() {
  const { user, logout, adopt } = useAuth()
  const pending = useSyncedQueue()
  const [trips, setTrips] = useState<DriverTrip[] | null>(null)
  const [params] = useSearchParams()
  const [starting, setStarting] = useState(false)
  const [later, setLater] = useState(false)

  useEffect(() => {
    api<DriverTrip[]>('/trips/mine').then(setTrips).catch(() => setTrips([]))
  }, [pending]) // refresh statuses after queued photos finish uploading

  const next = trips?.find((t) => OPEN.includes(t.pod_status))
  const onRoad = trips?.find((t) => t.state === 'in_transit' && OPEN.includes(t.pod_status))
  const focus = trips?.find((t) => t.id === params.get('trip')) ?? next // a message's link opens that trip's details
  const consent = user?.tracking_consent === true
  const gps = useTracker(onRoad?.id ?? null, consent && !!onRoad)
  const loc = LOC[user?.language ?? 'en']

  async function allow() {
    await api('/tracking/consent', { method: 'POST' })
    const me = await api<User>('/auth/me')
    adopt(tokenStore.get() ?? '', me)
  }

  async function start(id: string) {
    setStarting(true)
    try {
      const updated = await api<DriverTrip>(`/trips/${id}/start`, { method: 'POST' })
      setTrips((all) => all?.map((t) => (t.id === id ? { ...t, ...updated } : t)) ?? null)
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-full max-w-md flex-col px-5 pb-8 pt-6">
      <header className="flex items-center justify-between">
        <p className="text-lg font-medium">{user?.name}</p>
        <div className="flex items-center">
          {gps === 'on' && <span role="status" aria-label={loc.on} title={loc.on} className="mr-1 grid h-10 w-10 place-items-center rounded-full bg-ok-soft text-ok"><MapPin size={20} aria-hidden /></span>}
          <Link to="/driver/expense" aria-label="Expenses" className="grid h-12 w-12 place-items-center rounded-full text-muted"><Wallet aria-hidden /></Link>
          <Link to="/driver/pin" aria-label="PIN" className="grid h-12 w-12 place-items-center rounded-full text-muted"><KeyRound aria-hidden /></Link>
          <button onClick={logout} aria-label="Sign out" className="grid h-12 w-12 place-items-center rounded-full text-muted">
            <LogOut aria-hidden />
          </button>
        </div>
      </header>

      <InstallBanner />
      <DriverInbox />

      {onRoad && !consent && !later && (
        <section aria-label={loc.title} className="mt-4 space-y-3 rounded-2xl border border-line p-4">
          <p className="flex items-center gap-2 font-semibold"><MapPin size={20} aria-hidden /> {loc.title}</p>
          <p className="text-sm text-muted">{loc.body}</p>
          <div className="flex gap-3">
            <button onClick={() => void allow()} className="flex-1 rounded-xl bg-accent py-3 font-semibold text-on-solid">{loc.allow}</button>
            <button onClick={() => setLater(true)} className="flex-1 rounded-xl border border-line py-3 text-muted">{loc.later}</button>
          </div>
        </section>
      )}

      {pending > 0 && (
        <div className="mt-4 flex items-center gap-3 rounded-2xl bg-accent-soft p-4 text-accent" role="status">
          <CloudUpload aria-hidden /> <span className="text-lg font-semibold tabular-nums">{pending}</span>
        </div>
      )}

      {next?.state === 'planned' ? (
        <button onClick={() => void start(next.id)} disabled={starting}
          className="mt-6 grid h-48 w-full place-items-center rounded-3xl bg-ok text-on-solid active:scale-[0.98] disabled:opacity-60">
          <span className="flex flex-col items-center gap-3 text-xl font-semibold">
            <Play size={64} aria-hidden /> {START[user?.language ?? 'en']}
            <span className="text-base font-normal opacity-90">{next.destination}</span>
          </span>
        </button>
      ) : next ? (
        <Link to={`/driver/trip/${next.id}`}
          className="mt-6 grid h-48 w-full place-items-center rounded-3xl bg-accent text-on-solid active:scale-[0.98]">
          <span className="flex flex-col items-center gap-3 text-xl font-semibold">
            <Camera size={64} aria-hidden /> POD
            <span className="text-base font-normal opacity-90">{next.destination}</span>
          </span>
        </Link>
      ) : (
        trips && (
          <div className="mt-6 grid h-48 w-full place-items-center rounded-3xl bg-ok-soft text-ok">
            <CircleCheck size={80} aria-label="All done" />
          </div>
        )
      )}

      {focus && <DriverTripDetails trip={focus} />}

      <ul className="mt-8 space-y-3">
        {trips?.map((t) => {
          const { icon: Icon, cls, label } = statusIcon(t.pod_status)
          return (
            <li key={t.id} className="flex items-center gap-4 rounded-2xl border border-line p-4">
              <span className={`grid h-14 w-14 shrink-0 place-items-center rounded-full ${cls}`} title={label}>
                <Icon size={28} aria-label={label} />
              </span>
              <div className="min-w-0">
                <div className="truncate text-lg font-semibold">{t.destination}</div>
                <div className="truncate text-sm text-muted">{t.trip_code} · {t.vehicle}</div>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
