import { ListChecks, LogOut, Truck } from 'lucide-react'
import { Link, NavLink } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useEffect, useState, type ReactNode } from 'react'
import { api, type ReviewItem } from '../lib/api'

function useReviewCount(enabled: boolean): number {
  const [n, setN] = useState(0)
  useEffect(() => {
    if (!enabled) return
    api<ReviewItem[]>('/review').then((r) => setN(r.length)).catch(() => undefined)
  }, [enabled])
  return n
}

export function OfficeShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
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
            {user?.role !== 'billing' && <NavLink to="/office" end className={link}>Dashboard</NavLink>}
            <NavLink to="/office/trips" className={link}>Trips</NavLink>
            {canReview && (
              <NavLink to="/office/review" className={link}>
                Review{reviewCount > 0 && <span className="ml-1.5 rounded-full bg-warn-soft px-1.5 text-xs text-warn">{reviewCount}</span>}
              </NavLink>
            )}
            {canReview && <NavLink to="/office/billing" className={link}>Billing</NavLink>}
            <NavLink to="/progress" className={link}>Build progress</NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="hidden text-muted sm:inline">{user?.name} · {user?.role}</span>
            <button onClick={logout} className="flex items-center gap-1.5 text-muted hover:text-ink" aria-label="Sign out">
              <LogOut size={16} aria-hidden /> <span className="hidden sm:inline">Sign out</span>
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
