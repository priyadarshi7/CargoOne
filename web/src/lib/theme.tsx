import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

/** Light / dark / follow-the-device. The saved choice is read by a tiny script in index.html before first paint. */
export type Theme = 'system' | 'light' | 'dark'
const STORE = 'cargoone.theme'
const query = () => matchMedia('(prefers-color-scheme: dark)')

function saved(): Theme {
  try {
    const v = localStorage.getItem(STORE)
    if (v === 'light' || v === 'dark' || v === 'system') return v
  } catch { /* blocked storage: follow the device */ }
  return 'system'
}

export const resolve = (t: Theme, deviceDark: boolean): 'light' | 'dark' => (t === 'system' ? (deviceDark ? 'dark' : 'light') : t)

function apply(t: Theme) {
  const mode = resolve(t, query().matches)
  document.documentElement.dataset.theme = mode
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', mode === 'dark' ? '#0c0c0d' : '#ffffff')
}

const Ctx = createContext<{ theme: Theme; setTheme: (t: Theme) => void }>({ theme: 'system', setTheme: () => undefined })

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(saved)
  useEffect(() => {
    apply(theme)
    if (theme !== 'system') return
    const q = query()
    const on = () => apply('system')
    q.addEventListener('change', on)
    return () => q.removeEventListener('change', on)
  }, [theme])
  const setTheme = useCallback((t: Theme) => {
    setThemeState(t)
    try { localStorage.setItem(STORE, t) } catch { /* not persisted */ }
  }, [])
  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useTheme = () => useContext(Ctx)
