import { en, type Key } from './en'
import { hi } from './hi'
import { mr } from './mr'
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

/** Office-screen translations. English is the source: every key must exist there, and hi/mr fall back to it for
 *  anything not yet translated, so a missing word shows English instead of a blank. The Hindi/Marathi wording is
 *  a first draft and needs review by a native speaker at Company A before go-live. */
export type { Key }
export type Lang = 'en' | 'hi' | 'mr'

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

const LOCALE: Record<Lang, string> = { en: 'en-IN', hi: 'hi-IN', mr: 'mr-IN' }

/** Day + short month (+ time), in the chosen language's own numerals and month names. */
export function fmtDate(lang: Lang, iso: string, withTime = false): string {
  return new Date(iso).toLocaleString(LOCALE[lang], withTime ? { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' } : { day: '2-digit', month: 'short' })
}

interface Ctx { lang: Lang; date: (iso: string, withTime?: boolean) => string; setLang: (l: Lang) => void; t: (key: Key, vars?: Record<string, string | number>) => string }
const I18n = createContext<Ctx>({ lang: 'en', date: (iso, wt) => fmtDate('en', iso, wt), setLang: () => undefined, t: (k, v) => translate('en', k, v) })

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initial)
  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    document.documentElement.lang = l
    try { localStorage.setItem(STORE, l) } catch { /* not persisted */ }
  }, [])
  const value = useMemo<Ctx>(() => ({ lang, setLang, date: (iso, wt) => fmtDate(lang, iso, wt), t: (k, v) => translate(lang, k, v) }), [lang, setLang])
  return <I18n.Provider value={value}>{children}</I18n.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useI18n = () => useContext(I18n)
