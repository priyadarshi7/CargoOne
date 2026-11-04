import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

/** Office-screen translations. English is the source: every key must exist there, and hi/mr fall back to it for
 *  anything not yet translated, so a missing word shows English instead of a blank. The Hindi/Marathi wording is
 *  a first draft and needs review by a native speaker at Company A before go-live. */
export type Lang = 'en' | 'hi' | 'mr'

const en = {
  'nav.dashboard': 'Dashboard', 'nav.trips': 'Trips', 'nav.review': 'Review', 'nav.billing': 'Billing', 'nav.import': 'Import', 'nav.drivers': 'Drivers', 'nav.progress': 'Build progress',
  'shell.signOut': 'Sign out', 'shell.language': 'Language',
  'common.loading': 'Loading…', 'common.close': 'Close',
  'status.pending': 'Awaiting POD', 'status.uploaded': 'Checking', 'status.verified': 'Verified', 'status.needs_review': 'Needs review',
  'status.retake_requested': 'Retake', 'status.rejected': 'Rejected', 'status.billed': 'Billed',
  'login.identifier': 'Email or phone', 'login.secret': 'Password or PIN', 'login.submit': 'Sign in', 'login.busy': 'Signing in…',
  'login.wrong': 'Wrong login or password.', 'login.offline': 'Cannot reach the server.', 'login.progress': 'See build progress',
  'trips.error': 'Could not load trips.', 'trips.total': 'Trips', 'trips.verified': 'Verified', 'trips.needsReview': 'Needs review', 'trips.retake': 'Retake',
  'trips.trip': 'Trip', 'trips.client': 'Client', 'trips.vehicle': 'Vehicle', 'trips.to': 'To', 'trips.freight': 'Freight', 'trips.delivered': 'Delivered',
  'trips.pod': 'POD', 'trips.uploadLink': 'Upload link', 'trips.hired': 'hired', 'trips.sendLink': 'Send link', 'trips.link': 'Link', 'trips.share': 'Share',
  'review.title': 'Review queue', 'review.sub': 'PODs the system will not verify on its own. Oldest first.', 'review.empty': 'Nothing waiting for review.',
  'review.error': 'Could not load the review queue.', 'review.hoursAgo': '{n} h ago', 'review.daysAgo': '{n} days ago',
} as const

export type Key = keyof typeof en

const hi: Partial<Record<Key, string>> = {
  'nav.dashboard': 'डैशबोर्ड', 'nav.trips': 'ट्रिप', 'nav.review': 'जाँच', 'nav.billing': 'बिलिंग', 'nav.import': 'आयात', 'nav.drivers': 'ड्राइवर', 'nav.progress': 'प्रगति',
  'shell.signOut': 'साइन आउट', 'shell.language': 'भाषा',
  'common.loading': 'लोड हो रहा है…', 'common.close': 'बंद करें',
  'status.pending': 'रसीद बाकी', 'status.uploaded': 'जाँच जारी', 'status.verified': 'सत्यापित', 'status.needs_review': 'जाँच ज़रूरी',
  'status.retake_requested': 'दोबारा फोटो', 'status.rejected': 'अस्वीकृत', 'status.billed': 'बिल बना',
  'login.identifier': 'ईमेल या फ़ोन', 'login.secret': 'पासवर्ड या पिन', 'login.submit': 'साइन इन', 'login.busy': 'साइन इन हो रहा है…',
  'login.wrong': 'लॉगिन या पासवर्ड गलत है।', 'login.offline': 'सर्वर से संपर्क नहीं हो पा रहा।', 'login.progress': 'प्रगति देखें',
  'trips.error': 'ट्रिप लोड नहीं हो सकीं।', 'trips.total': 'ट्रिप', 'trips.verified': 'सत्यापित', 'trips.needsReview': 'जाँच ज़रूरी', 'trips.retake': 'दोबारा फोटो',
  'trips.trip': 'ट्रिप', 'trips.client': 'ग्राहक', 'trips.vehicle': 'गाड़ी', 'trips.to': 'गंतव्य', 'trips.freight': 'भाड़ा', 'trips.delivered': 'डिलीवरी',
  'trips.pod': 'रसीद', 'trips.uploadLink': 'अपलोड लिंक', 'trips.hired': 'किराये की', 'trips.sendLink': 'लिंक भेजें', 'trips.link': 'लिंक', 'trips.share': 'साझा करें',
  'review.title': 'जाँच सूची', 'review.sub': 'वे रसीदें जिन्हें सिस्टम खुद सत्यापित नहीं करेगा। सबसे पुरानी पहले।', 'review.empty': 'जाँच के लिए कुछ बाकी नहीं है।',
  'review.error': 'जाँच सूची लोड नहीं हो सकी।', 'review.hoursAgo': '{n} घंटे पहले', 'review.daysAgo': '{n} दिन पहले',
}

const mr: Partial<Record<Key, string>> = {
  'nav.dashboard': 'डॅशबोर्ड', 'nav.trips': 'ट्रिप', 'nav.review': 'तपासणी', 'nav.billing': 'बिलिंग', 'nav.import': 'आयात', 'nav.drivers': 'ड्रायव्हर', 'nav.progress': 'प्रगती',
  'shell.signOut': 'साइन आउट', 'shell.language': 'भाषा',
  'common.loading': 'लोड होत आहे…', 'common.close': 'बंद करा',
  'status.pending': 'पावती बाकी', 'status.uploaded': 'तपासणी सुरू', 'status.verified': 'सत्यापित', 'status.needs_review': 'तपासणी आवश्यक',
  'status.retake_requested': 'पुन्हा फोटो', 'status.rejected': 'नाकारली', 'status.billed': 'बिल झाले',
  'login.identifier': 'ईमेल किंवा फोन', 'login.secret': 'पासवर्ड किंवा पिन', 'login.submit': 'साइन इन', 'login.busy': 'साइन इन होत आहे…',
  'login.wrong': 'लॉगिन किंवा पासवर्ड चुकीचा आहे.', 'login.offline': 'सर्व्हरशी संपर्क होत नाही.', 'login.progress': 'प्रगती पहा',
  'trips.error': 'ट्रिप लोड होऊ शकल्या नाहीत.', 'trips.total': 'ट्रिप', 'trips.verified': 'सत्यापित', 'trips.needsReview': 'तपासणी आवश्यक', 'trips.retake': 'पुन्हा फोटो',
  'trips.trip': 'ट्रिप', 'trips.client': 'ग्राहक', 'trips.vehicle': 'गाडी', 'trips.to': 'ठिकाण', 'trips.freight': 'भाडे', 'trips.delivered': 'डिलिव्हरी',
  'trips.pod': 'पावती', 'trips.uploadLink': 'अपलोड लिंक', 'trips.hired': 'भाड्याची', 'trips.sendLink': 'लिंक पाठवा', 'trips.link': 'लिंक', 'trips.share': 'शेअर करा',
  'review.title': 'तपासणी यादी', 'review.sub': 'ज्या पावत्या सिस्टम स्वतः सत्यापित करणार नाही. सर्वात जुनी आधी.', 'review.empty': 'तपासणीसाठी काहीही बाकी नाही.',
  'review.error': 'तपासणी यादी लोड होऊ शकली नाही.', 'review.hoursAgo': '{n} तासांपूर्वी', 'review.daysAgo': '{n} दिवसांपूर्वी',
}

const DICT: Record<Lang, Partial<Record<Key, string>>> = { en, hi, mr }
export const LANGUAGES: [Lang, string][] = [['en', 'English'], ['hi', 'हिन्दी'], ['mr', 'मराठी']]
const STORE = 'cargoone.lang'

function initial(): Lang {
  try {
    const v = localStorage.getItem(STORE)
    if (v === 'hi' || v === 'mr' || v === 'en') return v
  } catch { /* storage blocked: English */ }
  return 'en'
}

/** Pure lookup, exported for tests: fall back to English, then substitute {placeholders}. */
export function translate(lang: Lang, key: Key, vars?: Record<string, string | number>): string {
  const text = DICT[lang][key] ?? en[key]
  return vars ? text.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? '')) : text
}

interface Ctx { lang: Lang; setLang: (l: Lang) => void; t: (key: Key, vars?: Record<string, string | number>) => string }
const I18n = createContext<Ctx>({ lang: 'en', setLang: () => undefined, t: (k, v) => translate('en', k, v) })

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initial)
  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    document.documentElement.lang = l
    try { localStorage.setItem(STORE, l) } catch { /* not persisted */ }
  }, [])
  const value = useMemo<Ctx>(() => ({ lang, setLang, t: (k, v) => translate(lang, k, v) }), [lang, setLang])
  return <I18n.Provider value={value}>{children}</I18n.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useI18n = () => useContext(I18n)
