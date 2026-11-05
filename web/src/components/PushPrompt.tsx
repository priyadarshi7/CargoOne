import { BellRing } from 'lucide-react'
import { useState } from 'react'
import { useI18n } from '../lib/i18n'
import { usePush } from '../lib/push'

const KEY = 'cargoone.alerts.dismissed'
const read = () => { try { return localStorage.getItem(KEY) === '1' } catch { return false } }

/** Offered once on the driver home: one big button to turn alerts on. Hidden when alerts are on, impossible on this phone, or the driver said "not now". */
export default function PushPrompt() {
  const { t } = useI18n()
  const { state, enable } = usePush()
  const [hidden, setHidden] = useState(read)
  if (hidden || state !== 'off') return null
  const later = () => { try { localStorage.setItem(KEY, '1') } catch { /* it just shows again */ } setHidden(true) }
  return (
    <section aria-label={t('drv.alerts.title')} className="mb-4 space-y-3 rounded-2xl border border-line bg-accent-soft p-4">
      <p className="flex items-center gap-2 text-lg font-semibold"><BellRing size={22} aria-hidden /> {t('drv.alerts.title')}</p>
      <p className="text-base text-ink/80">{t('drv.alerts.body')}</p>
      <div className="grid grid-cols-2 gap-3">
        <button onClick={() => void enable()} className="h-14 rounded-xl bg-ink text-lg font-semibold text-surface">{t('drv.alerts.on')}</button>
        <button onClick={later} className="h-14 rounded-xl border border-line bg-surface text-lg text-muted">{t('drv.alerts.later')}</button>
      </div>
    </section>
  )
}
