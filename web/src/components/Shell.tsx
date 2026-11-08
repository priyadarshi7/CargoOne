import { BarChart3, ClipboardCheck, FlaskConical, Home, Inbox, ListChecks, LogOut, Map, Menu, Receipt, ReceiptText, Route, Settings, Truck, Upload, UserRound, X, type LucideIcon } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { api, type ReviewItem } from '../lib/api'
import { ThemeToggle } from './ThemeToggle'
import { useAuth } from '../lib/auth'
import { LANGUAGES, useI18n } from '../lib/i18n'

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

/** New client requests waiting for the office. Checked every 30 s and when the tab is opened again, and shown in the tab title too. */
function useNewRequests(enabled: boolean): number {
  const [n, setN] = useState(0)
  const { pathname } = useLocation()
  useEffect(() => {
    if (!enabled) return
    const read = () => { api<{ requests_attention: number }>('/home').then((h) => setN(h.requests_attention)).catch(() => undefined) }
    read()
    const timer = window.setInterval(read, 30_000)
    const onShow = () => { if (document.visibilityState === 'visible') read() }
    document.addEventListener('visibilitychange', onShow)
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', onShow) }
  }, [enabled, pathname])
  useEffect(() => {
    const base = document.title.replace(/^\(\d+\) /, '')
    document.title = n > 0 ? `(${n}) ${base}` : base
    return () => { document.title = base }
  }, [n])
  return n
}

interface Item { to: string; label: string; icon: LucideIcon; end?: boolean; count?: number }
interface Group { title: string; items: Item[] }

/** The office app frame: a left sidebar grouped by kind of work (a drawer on phones), a slim top bar, then the page. */
export function OfficeShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const { t, lang, setLang } = useI18n()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const role = user?.role
  const canReview = role === 'billing' || role === 'ops' || role === 'admin'
  const canMap = role === 'ops' || role === 'md' || role === 'admin'
  const reviewCount = useReviewCount(canReview)
  const newRequests = useNewRequests(role === 'ops' || role === 'billing')
  useEffect(() => { setOpen(false) }, [pathname]) // a tapped link closes the drawer

  const groups: Group[] = [
    { title: t('nav.g.work'), items: [
      { to: '/office', label: role === 'md' ? t('nav.dashboard') : t('nav.today'), icon: Home, end: true },
      ...(role === 'ops' || role === 'admin' ? [{ to: '/office/performance', label: t('nav.performance'), icon: BarChart3 }] : []),
      { to: '/office/trips', label: t('nav.trips'), icon: Truck },
      ...(canReview ? [{ to: '/office/requests', label: t('nav.requests'), icon: Inbox, count: newRequests }, { to: '/office/planning', label: t('nav.planning'), icon: Route }] : []),
      ...(canMap ? [{ to: '/office/live', label: t('nav.live'), icon: Map }] : []),
    ] },
    { title: t('nav.g.money'), items: [
      ...(canReview ? [{ to: '/office/review', label: t('nav.review'), icon: ClipboardCheck, count: reviewCount }, { to: '/office/billing', label: t('nav.billing'), icon: Receipt }] : []),
      { to: '/office/expenses', label: t('nav.expenses'), icon: ReceiptText },
    ] },
    ...(canReview ? [{ title: t('nav.g.admin'), items: [{ to: '/office/setup', label: t('nav.setup'), icon: Settings }, { to: '/office/import', label: t('nav.import'), icon: Upload }, { to: '/office/benchmark', label: t('nav.benchmark'), icon: FlaskConical }] }] : []),
  ]
  const link = ({ isActive }: { isActive: boolean }) =>
    `flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium ${isActive ? 'border border-line bg-surface text-ink' : 'border border-transparent text-muted hover:bg-line/60 hover:text-ink'}`

  return (
    <div className="flex min-h-full">
      {open && <button aria-label={t('shell.closeMenu')} onClick={() => setOpen(false)} className="fixed inset-0 z-30 bg-black/40 lg:hidden" />}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col gap-6 border-r border-line bg-wash px-3 py-4 transition-transform lg:sticky lg:top-0 lg:h-screen lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex items-center justify-between px-2">
          <Link to="/office" className="flex items-center gap-2.5 text-base font-semibold tracking-tight">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-ink text-surface"><Truck size={16} aria-hidden /></span> CargoOne
          </Link>
          <button onClick={() => setOpen(false)} aria-label={t('shell.closeMenu')} className="grid h-9 w-9 place-items-center rounded-lg text-muted hover:text-ink lg:hidden"><X size={18} aria-hidden /></button>
        </div>
        <nav aria-label={t('shell.mainNav')} className="flex flex-1 flex-col gap-5 overflow-y-auto">
          {groups.map((g) => (
            <div key={g.title} className="space-y-1">
              <div className="px-3 pb-1 text-[11px] font-medium uppercase tracking-wider text-muted">{g.title}</div>
              {g.items.map(({ to, label, icon: Icon, end, count }) => (
                <NavLink key={to} to={to} end={end} className={link}>
                  <Icon size={18} aria-hidden /> {label}
                  {!!count && count > 0 && <span className="ml-auto grid min-w-5 place-items-center rounded-full bg-ink px-1.5 text-[11px] font-semibold text-surface">{count}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <Link to="/office/account" title="Account" aria-label="Account" className="flex items-center gap-3 rounded-lg border border-transparent p-2 hover:border-line hover:bg-surface">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-line bg-surface text-muted"><UserRound size={17} aria-hidden /></span>
          <span className="min-w-0 text-left"><span className="block truncate text-sm font-medium">{user?.name}</span><span className="block text-xs capitalize text-muted">{user?.role}</span></span>
        </Link>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-line bg-surface/90 px-4 backdrop-blur sm:px-6">
          <button onClick={() => setOpen(true)} aria-label={t('shell.menu')} className="grid h-9 w-9 place-items-center rounded-lg border border-line lg:hidden"><Menu size={18} aria-hidden /></button>
          <span className="text-sm font-semibold tracking-tight lg:hidden">CargoOne</span>
          <div className="ml-auto flex items-center gap-1.5 text-sm">
            <select value={lang} onChange={(e) => setLang(e.target.value as typeof lang)} aria-label={t('shell.language')} className="h-9 rounded-lg border border-line bg-surface px-2 text-sm text-muted">
              {LANGUAGES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
            </select>
            <ThemeToggle />
            <button onClick={logout} className="flex h-9 items-center gap-2 rounded-lg px-2.5 text-muted hover:bg-wash hover:text-ink" aria-label="Sign out">
              <LogOut size={16} aria-hidden /> <span className="hidden sm:inline">{t('shell.signOut')}</span>
            </button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-8">{children}</main>
      </div>
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
