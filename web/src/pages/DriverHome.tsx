import { Camera, CircleCheck, Clock, Eye, FileCheck2, MapPin, Navigation, Phone, Play, RotateCcw, Volume2, XCircle, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import DriverInbox from '../components/DriverInbox'
import DriverShell from '../components/DriverShell'
import StaleNote from '../components/StaleNote'
import DriverTripDetails from '../components/DriverTripDetails'
import InstallBanner from '../components/InstallBanner'
import PushPrompt from '../components/PushPrompt'
import { api, tokenStore, type DriverTrip, type PodStatus, type User } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useSyncedQueue } from '../lib/capture/sync'
import { useI18n } from '../lib/i18n'
import { useCachedApi } from '../lib/offline/cache'
import { enqueueAction, flushOutbox } from '../lib/offline/outbox'
import { useTracker } from '../lib/tracker'

const OPEN: PodStatus[] = ['pending', 'retake_requested']
const ICON: Record<PodStatus, { icon: LucideIcon; cls: string }> = {
  pending: { icon: Camera, cls: 'bg-wash text-muted' }, uploaded: { icon: Clock, cls: 'bg-accent-soft text-accent' }, verified: { icon: CircleCheck, cls: 'bg-ok-soft text-ok' },
  needs_review: { icon: Eye, cls: 'bg-warn-soft text-warn' }, retake_requested: { icon: RotateCcw, cls: 'bg-warn-soft text-warn' }, rejected: { icon: XCircle, cls: 'bg-bad-soft text-bad' },
  billed: { icon: FileCheck2, cls: 'bg-ok-soft text-ok' },
}
const LOC: Record<'en' | 'hi' | 'mr', Record<'title' | 'body' | 'allow' | 'later' | 'on', string>> = {
  en: { title: 'Share your location during trips?', body: 'The office sees where your truck is, only while a trip is running. You can stop any time.', allow: 'Allow', later: 'Not now', on: 'Location on' },
  hi: { title: 'यात्रा के दौरान अपनी लोकेशन साझा करें?', body: 'दफ़्तर को सिर्फ़ यात्रा चलने के समय आपकी गाड़ी की जगह दिखेगी। आप कभी भी बंद कर सकते हैं।', allow: 'अनुमति दें', later: 'अभी नहीं', on: 'लोकेशन चालू' },
  mr: { title: 'प्रवासादरम्यान तुमचे लोकेशन शेअर करायचे?', body: 'कार्यालयाला फक्त प्रवास सुरू असताना तुमच्या गाडीची जागा दिसेल. तुम्ही केव्हाही बंद करू शकता.', allow: 'परवानगी द्या', later: 'आत्ता नाही', on: 'लोकेशन चालू' },
}
const SPEECH = { en: 'en-IN', hi: 'hi-IN', mr: 'mr-IN' } as const
const big = 'flex w-full items-center justify-center gap-3 rounded-2xl text-xl font-semibold active:scale-[0.98]'

/** Driver home. One trip, one big button. Everything works with no network: the trip list is the phone's saved copy, starting a trip
 *  is saved first and sent later, and photos wait in their own queue. */
export default function DriverHome() {
  const { user, adopt } = useAuth()
  const { t, lang } = useI18n()
  const pending = useSyncedQueue()
  const { data: trips, stale, loaded, mutate } = useCachedApi<DriverTrip[]>('/trips/mine', user?.id ?? 'anon', pending) // refresh statuses after queued photos finish
  const [params] = useSearchParams()
  const [starting, setStarting] = useState(false)
  const [later, setLater] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  const next = trips?.find((x) => OPEN.includes(x.pod_status) && x.state !== 'cancelled')
  const onRoad = trips?.find((x) => x.state === 'in_transit' && OPEN.includes(x.pod_status))
  const focus = trips?.find((x) => x.id === params.get('trip')) ?? next // a message's link opens that trip's details
  const consent = user?.tracking_consent === true
  const gps = useTracker(onRoad?.id ?? null, consent && !!onRoad)
  const loc = LOC[lang]
  const past = trips?.filter((x) => x.id !== next?.id) ?? []

  async function allow() {
    await api('/tracking/consent', { method: 'POST' })
    const me = await api<User>('/auth/me')
    adopt(tokenStore.get() ?? '', me)
  }

  async function start(id: string) {
    setStarting(true)
    await enqueueAction('start', { trip_id: id }) // safe on the phone first
    mutate((all) => all.map((x) => (x.id === id ? { ...x, state: 'in_transit' } : x)))
    const before = navigator.onLine
    await flushOutbox().catch(() => undefined)
    if (!before) setToast(t('drv.savedStart'))
    setStarting(false)
  }

  function listen(x: DriverTrip) {
    if (!('speechSynthesis' in window)) return
    const voices = window.speechSynthesis.getVoices()
    const wanted = SPEECH[lang]
    const voice = voices.find((v) => v.lang === wanted) ?? (lang === 'mr' ? voices.find((v) => v.lang === 'hi-IN') : undefined) // many phones have no Marathi voice
    const u = new SpeechSynthesisUtterance(t('drv.say', { from: x.origin, to: x.destination }))
    u.lang = voice?.lang ?? wanted
    if (voice) u.voice = voice
    u.rate = 0.9
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(u)
  }

  const phoneTo = (x: DriverTrip) => x.consignee_phone ? `tel:${x.consignee_phone}` : null

  return (
    <DriverShell>
      {stale && <StaleNote />}
      {toast && <p aria-live="polite" className="mb-4 rounded-xl bg-ok-soft px-4 py-3 text-base font-medium text-ok">{toast}</p>}
      <PushPrompt />
      <InstallBanner />
      <DriverInbox />

      {onRoad && !consent && !later && (
        <section aria-label={loc.title} className="mb-4 space-y-3 rounded-2xl border border-line p-4">
          <p className="flex items-center gap-2 text-lg font-semibold"><MapPin size={22} aria-hidden /> {loc.title}</p>
          <p className="text-base text-muted">{loc.body}</p>
          <div className="grid grid-cols-2 gap-3">
            <button onClick={() => void allow()} className="h-14 rounded-xl bg-ink text-lg font-semibold text-surface">{loc.allow}</button>
            <button onClick={() => setLater(true)} className="h-14 rounded-xl border border-line text-lg text-muted">{loc.later}</button>
          </div>
        </section>
      )}
      {gps === 'on' && <p role="status" aria-label={loc.on} title={loc.on} className="mb-4 flex items-center gap-2 text-sm font-medium text-ok"><MapPin size={16} aria-hidden /> {loc.on}</p>}

      {!loaded && <p className="py-10 text-center text-lg text-muted">…</p>}

      {loaded && !next && (
        <section className="grid place-items-center gap-4 rounded-3xl border border-line px-6 py-14 text-center">
          <span className="grid h-24 w-24 place-items-center rounded-full bg-ok-soft text-ok"><CircleCheck size={52} aria-label={t('drv.allDone')} /></span>
          <p className="text-2xl font-semibold">{(trips?.length ?? 0) === 0 ? t('drv.noTrip') : t('drv.allDone')}</p>
          <p className="text-base text-muted">{t('drv.noTripB')}</p>
        </section>
      )}

      {next && (
        <section aria-label={next.destination} className="space-y-4">
          <div className="rounded-3xl border border-line p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 space-y-1">
                <p className="text-sm text-muted">{t('drv.from')}</p>
                <p className="truncate text-xl font-medium">{next.origin}</p>
                <p className="pt-1 text-sm text-muted">{t('drv.to')}</p>
                <p className="break-words text-3xl font-semibold leading-tight tracking-tight">{next.destination}</p>
              </div>
              {'speechSynthesis' in window && (
                <button onClick={() => listen(next)} aria-label={t('drv.listen')} className="grid h-14 w-14 shrink-0 place-items-center rounded-full border border-line"><Volume2 size={26} aria-hidden /></button>
              )}
            </div>
            <p className="mt-4 text-sm text-muted">{next.trip_code} · {next.vehicle}</p>
          </div>

          {next.state === 'planned' ? (
            <button onClick={() => void start(next.id)} disabled={starting} className={`${big} h-24 bg-ok text-on-solid disabled:opacity-60`}>
              <Play size={36} aria-hidden /> {starting ? t('drv.starting') : t('drv.start')}
            </button>
          ) : (
            <Link to={`/driver/trip/${next.id}`} className={`${big} h-24 bg-ink text-surface`}>
              <Camera size={36} aria-hidden /> <span className="text-left leading-tight">{t('drv.photo')}<span className="block text-sm font-normal opacity-80">{t('drv.photoB')}</span></span>
            </Link>
          )}

          <div className="grid grid-cols-2 gap-3">
            <a href={`https://www.google.com/maps/dir/?api=1&destination=${next.destination_lat != null && next.destination_lng != null ? `${next.destination_lat},${next.destination_lng}` : encodeURIComponent(next.destination)}`} target="_blank" rel="noreferrer"
              className={`${big} h-16 border border-line text-lg`}><Navigation size={24} aria-hidden /> {t('drv.navigate')}</a>
            {phoneTo(next)
              ? <a href={phoneTo(next) ?? undefined} className={`${big} h-16 border border-line text-lg`}><Phone size={24} aria-hidden /> {t('drv.call')}</a>
              : <span className={`${big} h-16 border border-line text-lg opacity-40`} aria-disabled="true"><Phone size={24} aria-hidden /> {t('drv.call')}</span>}
          </div>
        </section>
      )}

      {focus && (
        <details className="mt-5 rounded-2xl border border-line" open={params.get('trip') === focus.id}>
          <summary className="flex min-h-14 cursor-pointer items-center px-4 text-lg font-semibold">{t('drv.details')}</summary>
          <DriverTripDetails trip={focus} />
        </details>
      )}

      {past.length > 0 && (
        <section className="mt-8 space-y-3" aria-label={t('drv.past')}>
          <h2 className="text-base font-semibold text-muted">{t('drv.past')}</h2>
          <ul className="space-y-2.5">
            {past.map((x) => {
              const { icon: Icon, cls } = ICON[x.pod_status]
              return (
                <li key={x.id} className="flex items-center gap-4 rounded-2xl border border-line p-3.5">
                  <span title={t(`drv.st.${x.pod_status}`)} className={`grid h-14 w-14 shrink-0 place-items-center rounded-full ${cls}`}><Icon size={28} aria-hidden /></span>
                  <div className="min-w-0">
                    <p className="truncate text-lg font-semibold">{x.destination}</p>
                    <p className="truncate text-sm text-muted">{t(`drv.st.${x.pod_status}`)} · {x.trip_code}</p>
                  </div>
                </li>
              )
            })}
          </ul>
        </section>
      )}
    </DriverShell>
  )
}
