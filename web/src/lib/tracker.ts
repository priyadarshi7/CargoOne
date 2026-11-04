import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api'

/** Live location from the driver's phone while a trip is on the road.
 *  - A fix is kept when it is 60 s after the last kept one, or 100 m away from it (battery-friendly, still a smooth line).
 *  - Fixes are sent in batches; on a bad connection they wait in localStorage and go with the next batch (the server
 *    ignores repeats, so retrying is always safe).
 *  - A browser (PWA) can only track while the app is open and the screen is on, so the screen is kept awake. */
export type TrackerStatus = 'off' | 'waiting' | 'on' | 'denied' | 'stopped'

interface Fix { lat: number; lng: number; accuracy_m: number | null; speed_kmh: number | null; recorded_at: string }
const KEEP_EVERY_MS = 60_000
const KEEP_AFTER_M = 100
const FLUSH_EVERY_MS = 30_000
const MAX_BUFFER = 500

const key = (tripId: string) => `cargoone.pings.${tripId}`
const load = (tripId: string): Fix[] => { try { return JSON.parse(localStorage.getItem(key(tripId)) ?? '[]') as Fix[] } catch { return [] } }
const save = (tripId: string, b: Fix[]) => { try { localStorage.setItem(key(tripId), JSON.stringify(b.slice(-MAX_BUFFER))) } catch { /* storage full or blocked */ } }

function metres(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const r = 6_371_000, rad = Math.PI / 180
  const dp = (b.lat - a.lat) * rad, dl = (b.lng - a.lng) * rad
  const h = Math.sin(dp / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dl / 2) ** 2
  return 2 * r * Math.asin(Math.sqrt(h))
}

export function useTracker(tripId: string | null, enabled: boolean): TrackerStatus {
  const [status, setStatus] = useState<TrackerStatus>('off')
  const live = useRef(false)

  useEffect(() => {
    if (!enabled || !tripId || !('geolocation' in navigator)) return
    let stopped = false
    let last: Fix | null = null
    let lock: WakeLockSentinel | null = null
    setStatus('waiting')

    async function flush() {
      const buffer = load(tripId!)
      if (!buffer.length || stopped) return
      const batch = buffer.slice(0, 50)
      try {
        await api(`/trips/${tripId}/pings`, { method: 'POST', body: JSON.stringify({ pings: batch }) })
        save(tripId!, load(tripId!).slice(batch.length))
        live.current = true
        if (!stopped) setStatus('on')
      } catch (e) {
        if (e instanceof ApiError && (e.status === 403 || e.status === 409)) {
          stopped = true // consent withdrawn or the trip is no longer on the road: stop collecting
          save(tripId!, [])
          setStatus('stopped')
        } // anything else (offline, server error): keep the fixes and try again later
      }
    }

    const watch = navigator.geolocation.watchPosition(
      (p) => {
        const fix: Fix = {
          lat: p.coords.latitude, lng: p.coords.longitude, accuracy_m: p.coords.accuracy ?? null,
          speed_kmh: p.coords.speed != null && p.coords.speed >= 0 ? Math.round(p.coords.speed * 3.6) : null,
          recorded_at: new Date(p.timestamp).toISOString(),
        }
        const due = !last || new Date(fix.recorded_at).getTime() - new Date(last.recorded_at).getTime() >= KEEP_EVERY_MS || metres(last, fix) >= KEEP_AFTER_M
        if (!due) return
        const firstEver = !live.current
        last = fix
        save(tripId, [...load(tripId), fix])
        if (firstEver) void flush() // show the truck on the office map straight away
      },
      (err) => { if (err.code === err.PERMISSION_DENIED) setStatus('denied') },
      { enableHighAccuracy: true, maximumAge: 10_000, timeout: 30_000 },
    )
    const timer = setInterval(() => void flush(), FLUSH_EVERY_MS)

    const keepAwake = async () => { try { lock = (await navigator.wakeLock?.request('screen')) ?? null } catch { /* not supported or refused */ } }
    void keepAwake()
    const onVisible = () => { if (document.visibilityState === 'visible') { void keepAwake(); void flush() } }
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      stopped = true
      navigator.geolocation.clearWatch(watch)
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
      void lock?.release().catch(() => undefined)
    }
  }, [tripId, enabled])

  return enabled && tripId ? status : 'off'
}
