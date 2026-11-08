import { Check, Copy, Link2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, ApiError, type Trip } from '../lib/api'
import { useI18n } from '../lib/i18n'
import PhoneInput from './PhoneInput'

interface LinkOut { url: string; expires_at: string; sms_sent: boolean; sms_simulated: boolean; sms_error: string | null }
const LANGS = [['hi', 'हिन्दी'], ['mr', 'मराठी'], ['en', 'English']] as const

/** Office action: create a one-trip upload link for a hired driver and (optionally) "SMS" it.
 *  SMS is simulated in this build; the link is shown so it can also be shared by WhatsApp or read out. */
export function UploadLinkDialog({ trip, onClose }: { trip: Trip; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const { t, date } = useI18n()
  const [phone, setPhone] = useState('')
  const [name, setName] = useState('')
  const [lang, setLang] = useState<(typeof LANGS)[number][0]>('hi')
  const [link, setLink] = useState<LinkOut | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => { ref.current?.showModal() }, [])

  async function create() {
    setBusy(true)
    setError(null)
    try {
      setLink(await api<LinkOut>(`/trips/${trip.id}/upload-link`, {
        method: 'POST', body: JSON.stringify({ phone: phone.trim() || undefined, driver_name: name.trim() || undefined, lang }),
      }))
    } catch (e) {
      setError(e instanceof ApiError && e.status === 422 ? t('ul.phoneBad') : e instanceof ApiError ? e.message : t('ul.createFail'))
    } finally {
      setBusy(false)
    }
  }

  async function revoke() {
    await api(`/trips/${trip.id}/upload-link`, { method: 'DELETE' }).catch(() => undefined)
    setLink(null)
  }

  async function copy() {
    if (!link) return
    await navigator.clipboard?.writeText(link.url).catch(() => undefined)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const field = 'w-full rounded-lg border border-line px-3 py-2 text-sm outline-none focus:border-accent'
  return (
    <dialog ref={ref} onClose={onClose} aria-label={t('ul.title')}
      className="m-auto w-[min(32rem,92vw)] rounded-2xl border border-line p-0 shadow-xl backdrop:bg-black/30">
      <div className="space-y-5 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold"><Link2 size={18} aria-hidden /> {t('ul.title')}</h2>
            <p className="text-sm text-muted">{trip.trip_code} · {trip.destination} · {trip.vehicle}</p>
          </div>
          <button onClick={() => ref.current?.close()} aria-label={t('common.close')} className="text-muted hover:text-ink"><X size={20} /></button>
        </div>

        {!link ? (
          <>
            <p className="text-sm text-muted">{t('ul.intro')}</p>
            <PhoneInput label={t('ul.phone')} value={phone} onChange={setPhone} />
            <label className="block space-y-1 text-sm"><span className="text-muted">{t('ul.name')}</span>
              <input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} className={field} /></label>
            <fieldset className="space-y-1 text-sm">
              <legend className="text-muted">{t('ul.lang')}</legend>
              <div className="flex gap-2">
                {LANGS.map(([v, label]) => (
                  <button key={v} type="button" aria-pressed={lang === v} onClick={() => setLang(v)}
                    className={`rounded-lg border px-3 py-1.5 ${lang === v ? 'border-accent bg-accent-soft font-medium text-accent' : 'border-line text-muted'}`}>{label}</button>
                ))}
              </div>
            </fieldset>
            {error && <p role="alert" className="text-sm text-bad">{error}</p>}
            <button disabled={busy} onClick={() => void create()} className="w-full rounded-lg bg-ink py-2.5 font-medium text-surface disabled:opacity-60">
              {busy ? t('ul.creating') : phone.trim() ? t('ul.createSms') : t('ul.create')}
            </button>
          </>
        ) : (
          <>
            <div className="flex gap-2">
              <input readOnly aria-label={t('ul.title')} value={link.url} className={`${field} font-mono text-xs`} onFocus={(e) => e.currentTarget.select()} />
              <button onClick={() => void copy()} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 text-sm hover:border-accent">
                {copied ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />} {copied ? t('ul.copied') : t('ul.copy')}
              </button>
            </div>
            <ul className="space-y-1 text-sm text-muted">
              {link.sms_sent && <li>{link.sms_simulated ? t('ul.smsSim') : t('ul.smsOk')}</li>}
              {link.sms_error && <li role="alert" className="text-bad">{t('ul.smsFail', { why: link.sms_error })}</li>}
              <li>{t('ul.valid', { when: date(link.expires_at, true) })}</li>
            </ul>
            <button onClick={() => void revoke()} className="text-sm text-bad underline underline-offset-2">{t('ul.revoke')}</button>
          </>
        )}
      </div>
    </dialog>
  )
}
