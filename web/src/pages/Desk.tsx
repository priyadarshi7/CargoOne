import { ArrowRight, Boxes, ClipboardCheck, FileClock, Inbox, Map, PackageSearch, Receipt, ReceiptText, Route, Truck, Upload, Users, type LucideIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Attention from '../components/Attention'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useLive } from '../lib/live'

interface Home {
  planned: number; in_transit: number; pod_missing: number; awaiting_review: number; requests_new: number; trucks_available: number
  expenses_pending: number; ready_to_bill: number; ready_amount: number | null
}
type Tone = 'warn' | 'plain'
interface TileDef { label: string; value: number; to: string; icon: LucideIcon; tone: Tone; extra?: string }
interface Action { label: string; to: string; icon: LucideIcon }

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })

function Tile({ label, value, to, icon: Icon, tone, extra }: TileDef) {
  const hot = tone === 'warn' && value > 0
  return (
    <Link to={to} className="group rounded-2xl border border-line p-4 transition-colors sm:p-5 hover:border-ink/30 hover:bg-wash">
      <div className="flex items-center justify-between">
        <span className={`grid h-9 w-9 place-items-center rounded-full ${hot ? 'bg-warn-soft text-warn' : 'bg-accent-soft text-accent'}`}><Icon size={18} aria-hidden /></span>
        <ArrowRight size={16} className="text-muted group-hover:text-accent" aria-hidden />
      </div>
      <div className="mt-4 text-3xl font-semibold tabular-nums">{value}</div>
      <div className="text-sm text-muted">{label}</div>
      {extra && <div className="mt-1 text-xs text-muted">{extra}</div>}
    </Link>
  )
}

function DeskFrame({ title, sub, tiles, actions, primary }: { title: string; sub: string; tiles: TileDef[] | null; actions: Action[]; primary: Action }) {
  const { t } = useI18n()
  const { user } = useAuth()
  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted">{t('desk.hello', { name: user?.name ?? '' })}</p>
          <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-1 text-sm text-muted">{sub}</p>
        </div>
        <Link to={primary.to} className="inline-flex h-11 items-center gap-2 rounded-xl bg-ink px-5 text-sm font-medium text-surface hover:opacity-90"><primary.icon size={16} aria-hidden /> {primary.label}</Link>
      </div>
      <Attention />
      {tiles === null ? <p className="text-muted">{t('common.loading')}</p> : (
        <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-3">{tiles.map((x) => <Tile key={x.to + x.label} {...x} />)}</div>
      )}
      <section aria-label={t('desk.actions')}>
        <h2 className="mb-3 font-semibold">{t('desk.actions')}</h2>
        <div className="flex flex-wrap gap-3">
          {actions.map(({ label, to, icon: Icon }) => (
            <Link key={to} to={to} className="inline-flex items-center gap-2 rounded-lg border border-line px-4 py-2.5 text-sm font-medium hover:border-accent hover:text-accent">
              <Icon size={16} aria-hidden /> {label}
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}

function useHome(): { data: Home | null; failed: boolean } {
  const [data, setData] = useState<Home | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => { api<Home>('/home').then(setData).catch(() => setFailed(true)) }, [])
  useLive(['trips', 'billing', 'requests', 'expenses', 'review'], () => { api<Home>('/home').then(setData).catch(() => undefined) })
  return { data, failed }
}

/** Ops head's home: what is moving, what is stuck, and the quick jumps to planning, requests and the fleet. */
function OpsDesk() {
  const { t } = useI18n()
  const { data, failed } = useHome()
  const tiles: TileDef[] | null = data && [
    { label: t('desk.t.requests'), value: data.requests_new, to: '/office/requests', icon: Inbox, tone: 'warn' },
    { label: t('desk.t.planned'), value: data.planned, to: '/office/trips', icon: Route, tone: 'plain' },
    { label: t('desk.t.inTransit'), value: data.in_transit, to: '/office/live', icon: Truck, tone: 'plain' },
    { label: t('desk.t.podMissing'), value: data.pod_missing, to: '/office/trips?pod=missing', icon: PackageSearch, tone: 'warn' },
    { label: t('desk.t.review'), value: data.awaiting_review, to: '/office/review', icon: ClipboardCheck, tone: 'warn' },
    { label: t('desk.t.trucks'), value: data.trucks_available, to: '/office/setup?tab=trucks', icon: Boxes, tone: 'plain' },
  ]
  return (
    <>
      {failed && <p className="mb-4 text-bad">{t('desk.loadFail')}</p>}
      <DeskFrame title={t('desk.ops.title')} sub={t('desk.ops.sub')} tiles={failed ? [] : tiles} primary={{ label: t('desk.a.plan'), to: '/office/planning', icon: Route }} actions={[
        { label: t('desk.a.requests'), to: '/office/requests', icon: Inbox },
        { label: t('desk.a.live'), to: '/office/live', icon: Map }, { label: t('desk.a.drivers'), to: '/office/setup?tab=drivers', icon: Users },
        { label: t('desk.a.trucks'), to: '/office/setup?tab=trucks', icon: Truck }, { label: t('desk.a.import'), to: '/office/import', icon: Upload },
      ]} />
    </>
  )
}

/** Billing executive's home: receipts waiting for a check, loads ready to invoice, expenses to approve. */
function BillingDesk() {
  const { t } = useI18n()
  const { data, failed } = useHome()
  const tiles: TileDef[] | null = data && [
    { label: t('desk.t.review'), value: data.awaiting_review, to: '/office/review', icon: ClipboardCheck, tone: 'warn' },
    { label: t('desk.t.ready'), value: data.ready_to_bill, to: '/office/billing', icon: FileClock, tone: 'warn',
      extra: data.ready_amount === null ? undefined : t('desk.t.readyAmt', { amt: inr.format(data.ready_amount) }) },
    { label: t('desk.t.podMissing'), value: data.pod_missing, to: '/office/trips?pod=missing', icon: PackageSearch, tone: 'warn' },
    { label: t('desk.t.expenses'), value: data.expenses_pending, to: '/office/expenses', icon: ReceiptText, tone: 'warn' },
  ]
  return (
    <>
      {failed && <p className="mb-4 text-bad">{t('desk.loadFail')}</p>}
      <DeskFrame title={t('desk.billing.title')} sub={t('desk.billing.sub')} tiles={failed ? [] : tiles} primary={{ label: t('desk.a.invoice'), to: '/office/billing', icon: Receipt }} actions={[
        { label: t('desk.a.review'), to: '/office/review', icon: ClipboardCheck },
        { label: t('desk.a.expenses'), to: '/office/expenses', icon: ReceiptText }, { label: t('desk.a.trips'), to: '/office/trips', icon: Route },
      ]} />
    </>
  )
}

/** The office home: the billing desk for billing executives, the operations desk for everyone else. One default export so the screen loads as one piece. */
export default function Desk({ billing }: { billing: boolean }) {
  return billing ? <BillingDesk /> : <OpsDesk />
}
