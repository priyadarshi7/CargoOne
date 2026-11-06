import { Check, Copy, MessageCircle, Send, X } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api, ApiError, fetchBlob, type Trip } from '../lib/api'
import { useI18n, type Key } from '../lib/i18n'

interface Row { kind: string; at: string; note: string | null; public: boolean; meta: { reason?: string; minutes?: number; eta?: string } | null }
interface Timeline {
  acknowledged_at: string | null; loaded_at: string | null; has_loading_photo: boolean; started_at: string | null
  delivery_confirmed_at: string | null; delivery_override: string | null; delivery_issue: boolean; delivery_note: string | null
  eway_valid_until: string | null; closed_at: string | null; events: Row[]
}

interface Link { url: string; to: string | null; has_phone: boolean; whatsapp: string | null }
interface Links { client: Link; receiver: Link; views: { client: number; receiver: number }; sent_status?: string | null }

/** The office's view of one shipment: where each step stands, the timeline in order, the loading photo, the addresses to share, and (for ops) delivering without the receiver's code. */
export function ShipmentDialog({ trip, canAct, canShare, onClose }: { trip: Trip; canAct: boolean; canShare: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const { t, date } = useI18n()
  const [tl, setTl] = useState<Timeline | null>(null)
  const [why, setWhy] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [links, setLinks] = useState<Links | null>(null)
  const [copied, setCopied] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const load = () => api<Timeline>(`/trips/${trip.id}/timeline`).then(setTl).catch(() => setError(t('sh.failed')))
  useEffect(() => {
    ref.current?.showModal(); void load()
    if (canShare) api<Links>(`/trips/${trip.id}/shipment-links`).then(setLinks).catch(() => undefined)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function copy(key: string, url: string) {
    await navigator.clipboard?.writeText(url).catch(() => undefined)
    setCopied(key)
    setTimeout(() => setCopied(null), 2000)
  }
  async function send(aud: 'client' | 'receiver') {
    setBusy(true); setError(null); setNote(null)
    try { const r = await api<Links>(`/trips/${trip.id}/shipment-links/send?audience=${aud}`, { method: 'POST' }); setLinks(r); setNote(t('sh.sentOk')) }
    catch (err) { setError(err instanceof ApiError ? err.message : t('sh.failed')) }
    finally { setBusy(false) }
  }
  async function retire() {
    setBusy(true); setError(null)
    try { setLinks(await api<Links>(`/trips/${trip.id}/shipment-links/retire`, { method: 'POST' })); setNote(t('sh.retired')) }
    catch (err) { setError(err instanceof ApiError ? err.message : t('sh.failed')) }
    finally { setBusy(false) }
  }

  async function photo() {
    try { window.open(URL.createObjectURL(await fetchBlob(`/trips/${trip.id}/loading-photo`)), '_blank', 'noopener') } catch { setError(t('sh.failed')) }
  }

  async function override(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try { await api(`/trips/${trip.id}/deliver`, { method: 'POST', body: JSON.stringify({ override_reason: why }) }); setWhy(''); await load() }
    catch (err) { setError(err instanceof ApiError ? err.message : t('sh.failed')) }
    finally { setBusy(false) }
  }

  const stat = (label: string, value: string, ok: boolean) => (
    <div className="flex items-center justify-between gap-3 py-2"><dt className="text-muted">{label}</dt><dd className={`font-medium ${ok ? 'text-ok' : 'text-warn'}`}>{value}</dd></div>
  )
  const detail = (r: Row) => {
    const bits = [r.meta?.reason ? t(`drv.r.${r.meta.reason}` as Key) : null, r.meta?.minutes ? t('drv.pMin', { n: r.meta.minutes }) : null, r.meta?.eta ? date(r.meta.eta, true) : null, r.note].filter(Boolean)
    return bits.length ? bits.join(' · ') : null
  }

  return (
    <dialog ref={ref} onClose={onClose} aria-label={t('sh.title')} className="m-auto max-h-[92vh] w-[min(34rem,94vw)] overflow-y-auto rounded-2xl border border-line bg-surface p-0 text-ink shadow-xl backdrop:bg-black/30">
      <div className="space-y-5 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">{t('sh.title')} {trip.trip_code}</h2>
            <p className="text-sm text-muted">{trip.client} · {trip.origin} → {trip.destination}</p>
          </div>
          <button onClick={() => ref.current?.close()} aria-label={t('common.close')} className="text-muted hover:text-ink"><X size={20} /></button>
        </div>

        {tl && (
          <>
            <dl className="divide-y divide-line text-sm">
              {stat(t('sh.seen'), tl.acknowledged_at ? date(tl.acknowledged_at, true) : t('sh.notYet'), !!tl.acknowledged_at)}
              {stat(t('sh.loadedAt'), tl.loaded_at ? date(tl.loaded_at, true) : t('sh.notYet'), !!tl.loaded_at)}
              {stat(t('sh.code'), tl.delivery_confirmed_at ? t('sh.confirmed') : t('sh.waiting'), !!tl.delivery_confirmed_at)}
              {tl.eway_valid_until && stat(t('sh.ewayUntil'), date(tl.eway_valid_until, true), new Date(tl.eway_valid_until).getTime() > Date.now())}
            </dl>
            {tl.has_loading_photo && <button onClick={() => void photo()} className="rounded-lg border border-line px-3 py-1.5 text-sm font-medium hover:border-accent hover:text-accent">{t('sh.photo')}</button>}

            {tl.events.length === 0 ? <p className="text-sm text-muted">{t('sh.empty')}</p> : (
              <ol className="space-y-3 border-l border-line pl-4 text-sm">
                {tl.events.map((r, i) => (
                  <li key={i} className="relative">
                    <span aria-hidden className="absolute -left-[1.3rem] top-1.5 h-2 w-2 rounded-full bg-ink" />
                    <p className="font-medium">{t(`ev.${r.kind}` as Key)} <span className="font-normal text-muted">· {date(r.at, true)}</span></p>
                    {detail(r) && <p className="text-muted">{detail(r)}</p>}
                  </li>
                ))}
              </ol>
            )}

            {canAct && !tl.delivery_confirmed_at && trip.state !== 'cancelled' && (
              <form onSubmit={(e) => void override(e)} className="space-y-2 rounded-xl border border-line p-3">
                <label className="block space-y-1.5 text-sm"><span className="font-medium">{t('sh.override')}</span>
                  <input required minLength={3} maxLength={200} value={why} onChange={(e) => setWhy(e.target.value)} placeholder={t('sh.overrideWhy')} className="h-11 w-full rounded-lg border border-line bg-surface px-3.5 text-sm outline-none focus:border-ink" />
                </label>
                <button disabled={busy || why.trim().length < 3} className="rounded-lg border border-line px-4 py-2 text-sm font-medium hover:border-accent hover:text-accent disabled:opacity-50">{t('sh.overrideGo')}</button>
              </form>
            )}
          </>
        )}
        {links && (
          <section aria-label={t('sh.links')} className="space-y-3 border-t border-line pt-4">
            <h3 className="font-semibold">{t('sh.links')}</h3>
            <p className="text-sm text-muted">{t('sh.linksHelp')}</p>
            {(['client', 'receiver'] as const).map((aud) => (
              <div key={aud} className="space-y-1.5 rounded-xl border border-line p-3 text-sm">
                <p className="flex flex-wrap items-center justify-between gap-2 font-medium">{t(`sh.${aud}`)}{links[aud].to ? ` · ${links[aud].to}` : ''}<span className="text-xs font-normal text-muted">{t('sh.opens', { n: links.views[aud] })}</span></p>
                <div className="flex gap-2">
                  <input readOnly aria-label={`${t(`sh.${aud}`)} link`} value={links[aud].url} onFocus={(e) => e.currentTarget.select()} className="w-full rounded-lg border border-line px-3 py-2 font-mono text-xs outline-none" />
                  <button type="button" onClick={() => void copy(aud, links[aud].url)} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 hover:border-accent">{copied === aud ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />} {copied === aud ? t('ul.copied') : t('ul.copy')}</button>
                </div>
                {links[aud].has_phone ? (
                  <div className="flex flex-wrap gap-2">
                    <a href={links[aud].whatsapp ?? undefined} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-medium hover:border-accent hover:text-accent"><MessageCircle size={14} aria-hidden /> {t('sh.wa')}</a>
                    <button type="button" disabled={busy} onClick={() => void send(aud)} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-medium hover:border-accent hover:text-accent disabled:opacity-50"><Send size={14} aria-hidden /> {t('sh.send')}</button>
                  </div>
                ) : <p className="text-xs text-muted">{t('sh.noPhone')}</p>}
              </div>
            ))}
            <button type="button" disabled={busy} onClick={() => void retire()} className="text-sm text-bad underline underline-offset-2">{t('sh.retire')}</button>
          </section>
        )}
        {note && <p role="status" className="text-sm text-ok">{note}</p>}
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      </div>
    </dialog>
  )
}
