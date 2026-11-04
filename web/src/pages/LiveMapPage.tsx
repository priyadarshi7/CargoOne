import { Check, Copy, Share2, TriangleAlert, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { LiveMap, type MapPoint } from '../components/LiveMap'
import { api, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'

interface Live {
  trip_id: string; trip_code: string; vehicle: string; driver: string | null; origin: string; destination: string
  lat: number | null; lng: number | null; speed_kmh: number | null; seen_at: string | null
  state: 'moving' | 'stopped' | 'no_signal' | 'unknown'; minutes: number; alert: 'stoppage' | 'silent' | null
}

const TONE = { moving: 'ok', stopped: 'warn', no_signal: 'bad', unknown: 'muted' } as const
const REFRESH_MS = 20_000

/** Ops/MD view: every truck that is on the road, on a map and in a list, refreshed every 20 s. */
export default function LiveMapPage() {
  const { t } = useI18n()
  const { user } = useAuth()
  const canShare = user?.role === 'ops' || user?.role === 'admin'
  const [rows, setRows] = useState<Live[] | null>(null)
  const [error, setError] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [share, setShare] = useState<Live | null>(null)

  const load = useCallback(() => api<Live[]>('/tracking/live').then((r) => { setRows(r); setError(false) }).catch(() => setError(true)), [])
  useEffect(() => {
    void load()
    const id = setInterval(() => void load(), REFRESH_MS)
    return () => clearInterval(id)
  }, [load])

  const points = useMemo<MapPoint[]>(
    () => (rows ?? []).filter((r) => r.lat !== null && r.lng !== null).map((r) => ({ id: r.trip_id, lat: r.lat!, lng: r.lng!, label: `${r.trip_code} · ${r.vehicle}`, tone: r.alert ? 'bad' : TONE[r.state] })),
    [rows],
  )
  const ago = (iso: string) => {
    const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60_000))
    return m === 0 ? t('live.justNow') : t('live.seen', { n: m })
  }
  const status = (r: Live) => r.state === 'moving' ? t('live.moving') : r.state === 'stopped' ? t('live.stopped', { n: r.minutes }) : r.state === 'no_signal' ? t('live.noSignal', { n: r.minutes }) : t('live.unknown')

  if (error && !rows) return <p className="text-bad">{t('live.error')}</p>
  if (!rows) return <p className="text-muted">{t('common.loading')}</p>
  const alerts = rows.filter((r) => r.alert).length

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t('live.title')}</h1>
        <p className="text-sm text-muted">{t('live.sub')}</p>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:max-w-md">
        <div className="rounded-xl border border-line p-4"><div className="text-2xl font-semibold tabular-nums">{rows.length}</div><div className="text-sm text-muted">{t('live.onRoad')}</div></div>
        <div className="rounded-xl border border-line p-4"><div className={`text-2xl font-semibold tabular-nums ${alerts ? 'text-bad' : ''}`}>{alerts}</div><div className="text-sm text-muted">{t('live.alerts')}</div></div>
      </div>

      {rows.length === 0 ? (
        <p className="rounded-xl border border-line py-16 text-center text-muted">{t('live.none')}</p>
      ) : (
        <div className="grid gap-4 lg:h-[34rem] lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <ul className="divide-y divide-line overflow-y-auto rounded-xl border border-line">
            {rows.map((r) => (
              <li key={r.trip_id} className={selected === r.trip_id ? 'bg-accent-soft' : ''}>
                <div className="flex items-start gap-3 px-4 py-3">
                  <button onClick={() => setSelected(r.trip_id)} className="min-w-0 flex-1 text-left" aria-label={`${r.trip_code} ${r.vehicle}`}>
                    <div className="flex items-center gap-2 font-medium">{r.trip_code}
                      {r.alert && <span className="inline-flex items-center gap-1 rounded-full bg-bad-soft px-2 py-0.5 text-xs font-medium text-bad"><TriangleAlert size={12} aria-hidden />{r.alert === 'stoppage' ? t('live.alertStoppage') : t('live.alertSilent')}</span>}
                    </div>
                    <div className="truncate text-sm text-muted">{r.vehicle}{r.driver ? ` · ${r.driver}` : ''} → {r.destination}</div>
                    <div className="mt-1 text-xs text-muted">
                      <span className={r.alert ? 'text-bad' : r.state === 'moving' ? 'text-ok' : ''}>{status(r)}</span>
                      {r.speed_kmh != null && r.state === 'moving' && ` · ${t('live.speed', { n: r.speed_kmh })}`}
                      {r.seen_at && ` · ${ago(r.seen_at)}`}
                    </div>
                  </button>
                  {canShare && <button onClick={() => setShare(r)} className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-line px-2 py-1 text-xs hover:border-accent hover:text-accent" title={t('live.share')}><Share2 size={14} aria-hidden /> {t('live.share')}</button>}
                </div>
              </li>
            ))}
          </ul>
          {points.length === 0 ? <p className="grid place-items-center rounded-xl border border-line text-muted">{t('live.noMap')}</p> : <LiveMap points={points} selectedId={selected} onSelect={setSelected} label={t('live.title')} />}
        </div>
      )}
      {share && <TrackLinkDialog row={share} onClose={() => setShare(null)} />}
    </div>
  )
}

function TrackLinkDialog({ row, onClose }: { row: Live; onClose: () => void }) {
  const { t, date } = useI18n()
  const ref = useRef<HTMLDialogElement>(null)
  const [link, setLink] = useState<{ url: string; expires_at: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  useEffect(() => { ref.current?.showModal() }, [])

  async function create() {
    setError(null)
    try { setLink(await api(`/trips/${row.trip_id}/track-link`, { method: 'POST' })) }
    catch (e) { setError(e instanceof ApiError ? e.message : t('live.createFail')) }
  }
  async function revoke() { await api(`/trips/${row.trip_id}/track-link`, { method: 'DELETE' }).catch(() => undefined); setLink(null) }
  async function copy() {
    if (!link) return
    await navigator.clipboard?.writeText(link.url).catch(() => undefined)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <dialog ref={ref} onClose={onClose} aria-label={t('live.shareTitle')} className="m-auto w-[min(32rem,92vw)] rounded-2xl border border-line p-0 shadow-xl backdrop:bg-black/30">
      <div className="space-y-5 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold"><Share2 size={18} aria-hidden /> {t('live.shareTitle')}</h2>
            <p className="text-sm text-muted">{row.trip_code} · {row.vehicle} → {row.destination}</p>
          </div>
          <button onClick={() => ref.current?.close()} aria-label={t('common.close')} className="text-muted hover:text-ink"><X size={20} /></button>
        </div>
        <p className="text-sm text-muted">{t('live.shareIntro')}</p>
        {link ? (
          <>
            <div className="flex gap-2">
              <input readOnly aria-label={t('live.shareTitle')} value={link.url} className="w-full rounded-lg border border-line px-3 py-2 font-mono text-xs outline-none" onFocus={(e) => e.currentTarget.select()} />
              <button onClick={() => void copy()} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 text-sm hover:border-accent">
                {copied ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />} {copied ? t('ul.copied') : t('ul.copy')}
              </button>
            </div>
            <p className="text-sm text-muted">{t('ul.valid', { when: date(link.expires_at, true) })}</p>
            <button onClick={() => void revoke()} className="text-sm text-bad underline underline-offset-2">{t('live.revoke')}</button>
          </>
        ) : (
          <button onClick={() => void create()} className="w-full rounded-lg bg-accent py-2.5 font-medium text-on-solid">{t('live.create')}</button>
        )}
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      </div>
    </dialog>
  )
}
