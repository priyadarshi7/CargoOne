import { ListChecks, LogOut, Monitor, Moon, Sun, Truck } from 'lucide-react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useEffect, useState, type ReactNode } from 'react'
import { api, type ReviewItem } from '../lib/api'
import { LANGUAGES, useI18n } from '../lib/i18n'
import { useTheme, type Theme } from '../lib/theme'

/** Re-reads the count on every navigation, so the badge never goes stale after an approval. */
function useReviewCount(enabled: boolean): number {
  const [n, setN] = useState(0)
  const { pathname } = useLocation()
  useEffect(() => {
    if (!enabled) return
    api<ReviewItem[]>('/review').then((r) => setN(r.length)).catch(() => undefined)
  }, [enabled, pathname])
  return n
}

export function OfficeShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const { t, lang, setLang } = useI18n()
  const { theme, setTheme } = useTheme()
  const nextTheme: Record<Theme, Theme> = { system: 'light', light: 'dark', dark: 'system' }
  const ThemeIcon = { system: Monitor, light: Sun, dark: Moon }[theme]
  const canReview = user?.role === 'billing' || user?.role === 'ops' || user?.role === 'admin'
  const reviewCount = useReviewCount(canReview)
  const link = ({ isActive }: { isActive: boolean }) =>
    `rounded-md px-3 py-1.5 text-sm ${isActive ? 'bg-accent-soft font-medium text-accent' : 'text-muted hover:text-ink'}`
  return (
    <div className="min-h-full">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3 sm:px-6">
          <Link to="/office" className="flex items-center gap-2 font-semibold">
            <Truck size={20} className="text-accent" aria-hidden /> CargoOne
          </Link>
          <nav className="flex gap-1">
            {user?.role !== 'billing' && <NavLink to="/office" end className={link}>{t('nav.dashboard')}</NavLink>}
            <NavLink to="/office/trips" className={link}>{t('nav.trips')}</NavLink>
            {canReview && (
              <NavLink to="/office/review" className={link}>
                {t('nav.review')}{reviewCount > 0 && <span className="ml-1.5 rounded-full bg-warn-soft px-1.5 text-xs text-warn">{reviewCount}</span>}
              </NavLink>
            )}
            {canReview && <NavLink to="/office/billing" className={link}>{t('nav.billing')}</NavLink>}
            {canReview && <NavLink to="/office/drivers" className={link}>{t('nav.drivers')}</NavLink>}
            {canReview && <NavLink to="/office/import" className={link}>{t('nav.import')}</NavLink>}
            <NavLink to="/progress" className={link}>{t('nav.progress')}</NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <button onClick={() => setTheme(nextTheme[theme])} aria-label={`Theme: ${theme}`} title={`Theme: ${theme}`} className="grid h-8 w-8 place-items-center rounded-md text-muted hover:text-ink">
              <ThemeIcon size={18} aria-hidden />
            </button>
            <select value={lang} onChange={(e) => setLang(e.target.value as typeof lang)} aria-label={t('shell.language')}
              className="rounded-md border border-line bg-surface px-1.5 py-1 text-sm text-muted">
              {LANGUAGES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
            </select>
            <Link to="/office/account" className="hidden text-muted hover:text-ink sm:inline" title="Account" aria-label="Account">{user?.name} · {user?.role}</Link>
            <button onClick={logout} className="flex items-center gap-1.5 text-muted hover:text-ink" aria-label="Sign out">
              <LogOut size={16} aria-hidden /> <span className="hidden sm:inline">{t('shell.signOut')}</span>
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">{children}</main>
    </div>
  )
}

export function PublicShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-full">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-3xl items-center gap-2 px-4 py-3 font-semibold sm:px-6">
          <ListChecks size={20} className="text-accent" aria-hidden /> CargoOne · Build progress
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">{children}</main>
    </div>
  )
}
