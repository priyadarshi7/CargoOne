import { CircleCheck, CircleDashed, LoaderCircle } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { PublicShell } from '../components/Shell'
import { useAuth } from '../lib/auth'
import { OfficeShell } from '../components/Shell'
import { parseRoadmap, summarize, type ItemState } from '../lib/roadmap'

const ICON: Record<ItemState, { el: typeof CircleCheck; cls: string }> = {
  done: { el: CircleCheck, cls: 'text-ok' },
  doing: { el: LoaderCircle, cls: 'text-warn' },
  todo: { el: CircleDashed, cls: 'text-muted' },
}

function Body() {
  const phases = useMemo(() => parseRoadmap(), [])
  const total = summarize(phases)
  const [api, setApi] = useState<'checking' | 'up' | 'down'>('checking')

  useEffect(() => {
    fetch('/api/health').then((r) => setApi(r.ok ? 'up' : 'down')).catch(() => setApi('down'))
  }, [])

  return (
    <div className="space-y-10">
      <section>
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">Build progress</h1>
            <p className="text-sm text-muted">Read live from docs/02-roadmap.md</p>
          </div>
          <div className="text-right">
            <div className="text-3xl font-semibold tabular-nums">{total.pct}%</div>
            <div className="text-sm text-muted">{total.done} done · {total.doing} in progress · {total.total} total</div>
          </div>
        </div>
        <div className="mt-4 h-2 overflow-hidden rounded-full bg-wash" role="progressbar" aria-valuenow={total.pct}>
          <div className="h-full bg-accent" style={{ width: `${total.pct}%` }} />
        </div>
        <p className="mt-3 text-sm text-muted">
          API:{' '}
          <span className={api === 'up' ? 'text-ok' : api === 'down' ? 'text-bad' : ''}>
            {api === 'up' ? 'running' : api === 'down' ? 'not reachable' : 'checking…'}
          </span>
        </p>
      </section>

      {phases.map((p) => {
        const s = summarize([p])
        return (
          <section key={p.title}>
            <div className="mb-3 flex items-baseline justify-between border-b border-line pb-2">
              <h2 className="font-semibold">{p.title}</h2>
              <span className="text-sm tabular-nums text-muted">{s.done}/{s.total}</span>
            </div>
            <ul className="space-y-2">
              {p.items.map((it, i) => {
                const { el: Icon, cls } = ICON[it.state]
                return (
                  <li key={i} className="flex gap-2.5 text-sm">
                    <Icon size={18} className={`mt-0.5 shrink-0 ${cls}`} aria-label={it.state} />
                    <span className={it.state === 'done' ? 'text-muted' : ''}>{it.text}</span>
                  </li>
                )
              })}
            </ul>
          </section>
        )
      })}
    </div>
  )
}

export default function Progress() {
  const { user } = useAuth()
  return user && user.role !== 'driver' ? (
    <OfficeShell><Body /></OfficeShell>
  ) : (
    <PublicShell><Body /></PublicShell>
  )
}
