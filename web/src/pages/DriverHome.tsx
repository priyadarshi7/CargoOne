import { Camera, CircleCheck, Clock, Eye, FileCheck2, Flag, KeyRound, MapPin, Navigation, PackageCheck, Phone, Play, TriangleAlert, RotateCcw, Volume2, XCircle, type LucideIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import DriverInbox from '../components/DriverInbox'
import { DeliveryCodeForm, RoadEventForm, Sheet } from '../components/DriverSheets'
import { compressPhoto } from '../lib/capture/compress'
import { getPosition } from '../lib/capture/geo'
import { stampText } from '../lib/capture/stamp'
import { serverNow, syncClock } from '../lib/serverClock'
import DriverShell from '../components/DriverShell'
import StaleNote from '../components/StaleNote'
import DriverTripDetails from '../components/DriverTripDetails'
import InstallBanner from '../components/InstallBanner'
import PushPrompt from '../components/PushPrompt'
import { api, tokenStore, type DriverTrip, type PodStatus, type User } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useDriverBase } from '../lib/driverBase'
import { useSyncedQueue } from '../lib/capture/sync'
import { useI18n } from '../lib/i18n'
import { useCachedApi } from '../lib/offline/cache'
import { enqueueAction, flushOutbox, useOutbox } from '../lib/offline/outbox'
import { useTracker } from '../lib/tracker'
import { useLive } from '../lib/live'

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
const EARLY_H = 3 // the server refuses a start earlier than this before the planned time
const big = 'flex w-full items-center justify-center gap-3 rounded-2xl text-xl font-semibold active:scale-[0.98]'

/** Driver home. One trip, one big button. Everything works with no network: the trip list is the phone's saved copy, starting a trip
 *  is saved first and sent later, and photos wait in their own queue. */
export default function DriverHome() {
  const { user, adopt } = useAuth()
  const { t, lang } = useI18n()
  const { path } = useDriverBase()
  const pending = useSyncedQueue()
  const { data: trips, stale, loaded, mutate, reload } = useCachedApi<DriverTrip[]>('/trips/mine', user?.id ?? 'anon', pending) // refresh statuses after queued photos finish
  const { waiting } = useOutbox()
  const { data: office } = useCachedApi<{ phone: string | null }>('/trips/office-contact', user?.id ?? 'anon')
  const [params] = useSearchParams()
  const [starting, setStarting] = useState(false)
  const [later, setLaterState] = useState(() => { try { return localStorage.getItem('cargoone.locLater') === new Date().toDateString() } catch { return false } })
  const setLater = (v: boolean) => { setLaterState(v); try { if (v) localStorage.setItem('cargoone.locLater', new Date().toDateString()) } catch { /* storage blocked: asked again next time */ } }
  const [toast, setToast] = useState<string | null>(null)
  const [sheet, setSheet] = useState<'deliver' | 'problem' | null>(null)
  const [saving, setSaving] = useState(false)
  const photoInput = useRef<HTMLInputElement>(null)
  const acked = useRef(new Set<string>())

  // What to show first: the truck on the road, then a delivery still waiting for its photo, then the earliest trip to come.
  const rank = (x: DriverTrip) => (x.state === 'in_transit' ? 0 : x.state === 'delivered' ? 1 : 2)
  const next = trips?.filter((x) => OPEN.includes(x.pod_status) && x.state !== 'cancelled')
    .sort((a, b) => rank(a) - rank(b) || (a.planned_start ?? '').localeCompare(b.planned_start ?? ''))[0]
  const onRoad = trips?.find((x) => x.state === 'in_transit' && OPEN.includes(x.pod_status))
  const focus = trips?.find((x) => x.id === params.get('trip')) ?? next // a message's link opens that trip's details
  const consent = user?.tracking_consent === true
  const gps = useTracker(onRoad?.id ?? null, consent && !!onRoad)
  const loc = LOC[lang]
  const others = trips?.filter((x) => x.id !== next?.id) ?? []
  const upcoming = others.filter((x) => x.state === 'planned').sort((a, b) => (a.planned_start ?? '').localeCompare(b.planned_start ?? ''))
  const waitingPhoto = others.filter((x) => x.state === 'delivered' && OPEN.includes(x.pod_status))
  const finished = others.filter((x) => x.state !== 'planned' && !waitingPhoto.includes(x))
  const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString(lang === 'en' ? 'en-IN' : `${lang}-IN`, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : t('drv.tbd'))

  // Saved actions (start, reached, a delay) have just reached the server: show what the server now says, not the phone's guess.
  const was = useRef(0)
  useLive(['trips', 'expenses'], reload)
  useEffect(() => { if (was.current > 0 && waiting === 0 && navigator.onLine) reload(); was.current = waiting }, [waiting, reload])

  // Look again when the app comes back to the front or the network returns, so a change made by the office shows up without a restart.
  useEffect(() => {
    const again = () => { if (document.visibilityState === 'visible' && navigator.onLine) reload() }
    document.addEventListener('visibilitychange', again)
    window.addEventListener('online', again)
    return () => { document.removeEventListener('visibilitychange', again); window.removeEventListener('online', again) }
  }, [reload])

  async function allow() {
    await api('/tracking/consent', { method: 'POST' })
    const me = await api<User>('/auth/me')
    adopt(tokenStore.get() ?? '', me)
  }

  // The office sees that the driver has opened the job. A courtesy signal, so it is not queued: it simply tries again next time.
  useEffect(() => {
    if (!navigator.onLine) return
    for (const x of trips ?? []) {
      if (x.state !== 'planned' || x.acknowledged_at || acked.current.has(x.id)) continue
      acked.current.add(x.id)
      api(`/trips/${x.id}/ack`, { method: 'POST' }).then(() => mutate((all) => all.map((v) => (v.id === x.id ? { ...v, acknowledged_at: new Date().toISOString() } : v)))).catch(() => acked.current.delete(x.id))
    }
  }, [trips, mutate])

  async function loadedPhoto(id: string, file: File) {
    setSaving(true)
    try {
      const [pos] = await Promise.all([getPosition(), syncClock()]) // the loading photo carries its date, time and place too
      const { at, fromServer } = serverNow()
      const photo = await compressPhoto(file, stampText(at, pos, fromServer))
      await enqueueAction('loaded', { trip_id: id }, photo) // safe on the phone first, like starting
      mutate((all) => all.map((x) => (x.id === id ? { ...x, loaded_at: new Date().toISOString() } : x)))
      const before = navigator.onLine
      await flushOutbox().catch(() => undefined)
      if (!before) setToast(t('drv.savedLoaded'))
    } finally { setSaving(false) }
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

  async function arrive(id: string) {
    setSaving(true)
    await enqueueAction('arrived', { trip_id: id }) // safe on the phone first
    mutate((all) => all.map((x) => (x.id === id ? { ...x, arrived_at: new Date().toISOString() } : x)))
    const before = navigator.onLine
    await flushOutbox().catch(() => undefined)
    if (!before) setToast(t('drv.savedArrived'))
    setSaving(false)
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

      {next && !consent && !later && (
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
            {next.state === 'planned' && <p className="mt-1 text-base font-medium">{t('drv.pickupAt')}: {when(next.planned_start)}</p>}
            {next.consignee_name && <p className="mt-1 text-base">{t('drv.toRecv')}: <span className="font-semibold">{next.consignee_name}</span></p>}
            <Steps trip={next} />
          </div>

          {next.state === 'planned' && !next.loaded_at ? (
            <>
              <input ref={photoInput} type="file" accept="image/*" capture="environment" aria-label={t('drv.loaded')} className="sr-only" tabIndex={-1}
                onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) void loadedPhoto(next.id, f) }} />
              <button onClick={() => photoInput.current?.click()} disabled={saving} className={`${big} h-24 bg-ok text-on-solid disabled:opacity-60`}>
                <PackageCheck size={36} aria-hidden /> <span className="text-left leading-tight">{t('drv.loaded')}<span className="block text-sm font-normal opacity-80">{t('drv.loadedB')}</span></span>
              </button>
            </>
          ) : next.state === 'planned' ? (
            <>
              {(() => {
                const from = next.planned_start ? new Date(new Date(next.planned_start).getTime() - EARLY_H * 3_600_000) : null
                const tooEarly = from !== null && Date.now() < from.getTime()
                return (
                  <>
                    <button onClick={() => void start(next.id)} disabled={starting || tooEarly} className={`${big} h-24 bg-ok text-on-solid disabled:opacity-60`}>
                      <Play size={36} aria-hidden /> {starting ? t('drv.starting') : t('drv.start')}
                    </button>
                    {tooEarly && from && <p role="status" className="text-center text-base text-muted">{t('drv.startFrom', { time: from.toLocaleString(lang === 'en' ? 'en-IN' : lang === 'hi' ? 'hi-IN' : 'mr-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) })}</p>}
                  </>
                )
              })()}
            </>
          ) : next.state === 'in_transit' && !next.arrived_at ? (
            <button onClick={() => void arrive(next.id)} disabled={saving} className={`${big} h-24 bg-ok text-on-solid disabled:opacity-60`}>
              <Flag size={36} aria-hidden /> <span className="text-left leading-tight">{t('drv.arrived')}<span className="block text-sm font-normal opacity-80">{t('drv.arrivedB')}</span></span>
            </button>
          ) : next.needs_code ? (
            <button onClick={() => setSheet('deliver')} className={`${big} h-24 bg-ok text-on-solid`}>
              <KeyRound size={36} aria-hidden /> <span className="text-left leading-tight">{t('drv.deliver')}<span className="block text-sm font-normal opacity-80">{t('drv.deliverB')}</span></span>
            </button>
          ) : (
            <Link to={path(`/driver/trip/${next.id}`)} className={`${big} h-24 bg-ink text-surface`}>
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
          {next.state === 'in_transit' && (
            <button onClick={() => setSheet('problem')} className={`${big} h-16 border border-line text-lg`}><TriangleAlert size={24} aria-hidden /> {t('drv.problem')}</button>
          )}
          {office?.phone && <a href={`tel:${office.phone}`} className={`${big} h-16 border border-line text-lg`}><Phone size={24} aria-hidden /> {t('drv.callOffice')}</a>}
        </section>
      )}

      {focus && (
        <details className="mt-5 rounded-2xl border border-line" open={params.get('trip') === focus.id}>
          <summary className="flex min-h-14 cursor-pointer items-center px-4 text-lg font-semibold">{t('drv.details')}</summary>
          <DriverTripDetails trip={focus} />
        </details>
      )}

      <TripGroup title={t('drv.waitingPhoto')} trips={waitingPhoto} to={(x) => path(`/driver/trip/${x.id}`)} line={(x) => `${t(`drv.st.${x.pod_status}`)} · ${x.trip_code}`} />
      <TripGroup title={t('drv.upcoming')} trips={upcoming} line={(x) => `${when(x.planned_start)} · ${x.trip_code}`} />
      <TripGroup title={t('drv.done')} trips={finished} line={(x) => `${x.state === 'cancelled' ? t('drv.cancelledTrip') : t(`drv.st.${x.pod_status}`)} · ${x.trip_code}`} />
      {sheet === 'deliver' && next && (
        <Sheet title={t('drv.deliver')} lang={lang} onClose={() => setSheet(null)}>
          <DeliveryCodeForm lang={lang} send={async (b) => { await api(`/trips/${next.id}/deliver`, { method: 'POST', body: JSON.stringify(b) }) }}
            onDone={() => { mutate((all) => all.map((x) => (x.id === next.id ? { ...x, needs_code: false, state: 'delivered', delivery_confirmed_at: new Date().toISOString() } : x))); setSheet(null) }} />
        </Sheet>
      )}
      {sheet === 'problem' && next && (
        <Sheet title={t('drv.problem')} lang={lang} onClose={() => setSheet(null)}>
          <RoadEventForm lang={lang} send={async (b) => { await enqueueAction('road', { trip_id: next.id, kind: b.kind, reason: b.reason, minutes: b.minutes ? String(b.minutes) : '' }); const before = navigator.onLine; await flushOutbox().catch(() => undefined); if (!before) setToast(t('drv.savedRoad')) }}
            onDone={() => { setSheet(null); if (navigator.onLine) setToast(t('drv.pSent')) }} />
        </Sheet>
      )}
    </DriverShell>
  )
}

/** Four dots for the four things that happen on a trip, so the driver sees where they are without reading. */
function Steps({ trip }: { trip: DriverTrip }) {
  const { t } = useI18n()
  const done = [!!trip.loaded_at, trip.state === 'in_transit' || trip.state === 'delivered', !!trip.arrived_at || trip.state === 'delivered', !!trip.delivery_confirmed_at || trip.state === 'delivered']
  const names = ['loaded', 'started', 'arrived', 'delivered'] as const
  return (
    <ol aria-label={trip.trip_code} className="mt-4 grid grid-cols-4 gap-2">
      {names.map((n, i) => (
        <li key={n} className="space-y-1.5 text-center">
          <span className={`block h-2 rounded-full ${done[i] ? 'bg-ok' : 'bg-line'}`} />
          <span className={`block text-xs ${done[i] ? 'font-semibold text-ok' : 'text-muted'}`}>{t(`drv.step.${n}`)}</span>
        </li>
      ))}
    </ol>
  )
}

function TripGroup({ title, trips, line, to }: { title: string; trips: DriverTrip[]; line: (x: DriverTrip) => string; to?: (x: DriverTrip) => string }) {
  if (trips.length === 0) return null
  return (
    <section className="mt-8 space-y-3" aria-label={title}>
      <h2 className="text-base font-semibold text-muted">{title}</h2>
      <ul className="space-y-2.5">
        {trips.map((x) => {
          const { icon: Icon, cls } = x.state === 'cancelled' ? { icon: XCircle, cls: 'bg-wash text-muted' } : ICON[x.pod_status]
          const body = (
            <>
              <span className={`grid h-14 w-14 shrink-0 place-items-center rounded-full ${cls}`}><Icon size={28} aria-hidden /></span>
              <div className="min-w-0">
                <p className="truncate text-lg font-semibold">{x.destination}</p>
                <p className="truncate text-sm text-muted">{line(x)}</p>
              </div>
            </>
          )
          return <li key={x.id}>{to ? <Link to={to(x)} className="flex items-center gap-4 rounded-2xl border border-line p-3.5 active:bg-wash">{body}</Link> : <div className="flex items-center gap-4 rounded-2xl border border-line p-3.5">{body}</div>}</li>
        })}
      </ul>
    </section>
  )
}
