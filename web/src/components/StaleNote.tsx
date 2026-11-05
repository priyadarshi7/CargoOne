import { useI18n } from '../lib/i18n'
import { useOnline } from '../lib/offline/online'

/** "Showing what is saved on your phone", and why: no network at all, or the phone has internet but the server does not answer. */
export default function StaleNote() {
  const { t } = useI18n()
  const online = useOnline()
  return <p aria-live="polite" className="mb-4 rounded-xl bg-warn-soft px-4 py-3 text-base font-medium text-warn">{t(online ? 'drv.staleServer' : 'drv.stale')}</p>
}
