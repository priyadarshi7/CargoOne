import { Download, Share, X } from 'lucide-react'
import { useSyncExternalStore, useState } from 'react'
import { useI18n } from '../lib/i18n'
import { clearInstallEvent, installEvent, subscribeInstall } from '../lib/install'

const T = {
  en: { title: 'Install CargoOne', body: 'Put it on your home screen. It opens fast and works with a weak network.', btn: 'Install', ios: 'Tap Share, then "Add to Home Screen".', hide: 'Not now' },
  hi: { title: 'CargoOne इंस्टॉल करें', body: 'इसे होम स्क्रीन पर रखें। यह जल्दी खुलता है और कमज़ोर नेटवर्क में भी चलता है।', btn: 'इंस्टॉल करें', ios: 'शेयर दबाएँ, फिर "Add to Home Screen" चुनें।', hide: 'अभी नहीं' },
  mr: { title: 'CargoOne इन्स्टॉल करा', body: 'हे होम स्क्रीनवर ठेवा. ते लवकर उघडते आणि कमकुवत नेटवर्कमध्येही चालते.', btn: 'इन्स्टॉल करा', ios: 'शेअर दाबा, मग "Add to Home Screen" निवडा.', hide: 'आत्ता नाही' },
} as const

const KEY = 'cargoone.install.dismissed'
const read = () => { try { return localStorage.getItem(KEY) === '1' } catch { return false } }

/** Offers to install the app on the driver's phone. Hidden once installed (or dismissed). iPhone has no install API, so it gets the two-step hint. */
export default function InstallBanner() {
  const { lang } = useI18n()
  const tx = T[lang]
  const evt = useSyncExternalStore(subscribeInstall, installEvent)
  const [hidden, setHidden] = useState(read)
  const standalone = window.matchMedia('(display-mode: standalone)').matches || ('standalone' in navigator && (navigator as { standalone?: boolean }).standalone === true)
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent)

  if (standalone || hidden || (!evt && !ios)) return null
  const dismiss = () => { try { localStorage.setItem(KEY, '1') } catch { /* private mode: it just shows again */ } setHidden(true) }
  async function install() {
    if (!evt) return
    await evt.prompt()
    if ((await evt.userChoice).outcome === 'accepted') clearInstallEvent()
  }

  return (
    <section aria-label={tx.title} className="relative mb-4 rounded-2xl border border-line bg-accent-soft p-4">
      <button onClick={dismiss} aria-label={tx.hide} className="absolute right-2 top-2 grid h-9 w-9 place-items-center rounded-full text-muted"><X size={18} aria-hidden /></button>
      <p className="pr-8 font-semibold">{tx.title}</p>
      <p className="mt-1 text-sm text-muted">{tx.body}</p>
      {evt ? (
        <button onClick={() => void install()} className="mt-3 inline-flex h-12 items-center gap-2 rounded-xl bg-ink px-5 text-base font-semibold text-surface"><Download size={18} aria-hidden /> {tx.btn}</button>
      ) : (
        <p className="mt-3 flex items-center gap-2 text-sm font-medium"><Share size={18} aria-hidden /> {tx.ios}</p>
      )}
    </section>
  )
}
