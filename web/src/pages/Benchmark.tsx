import { ArrowLeftRight, ArrowRight, CircleCheck, TriangleAlert, X, XCircle, type LucideIcon } from 'lucide-react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { ReasonChips } from '../components/ReasonChips'
import { api, fetchBlob } from '../lib/api'
import { useI18n, type Key } from '../lib/i18n'

type Status = 'pass' | 'unsafe' | 'friction' | 'different' | 'error'
interface Extraction {
  lr_no: string | null; consignee_stamp_present: boolean; signature_present: boolean; delivery_date: string | null; quantity_received: string | null
  total_quantity: string | null; items: { name: string | null; quantity: number | null; unit: string | null }[]; remarks: string | null
  shortage_or_damage: boolean; confidence: number; issues: string[]
}
interface Case {
  photo: string; sheet: string; cond: string; title: string; tags: string[]; do: string; judgement: boolean
  expected: { decision: string; accept: string[]; reasons: string[]; lr: string; stamp: boolean; signature: boolean; date: string | null; quantity: string; items: number[]; total: number | null; remarks: string }
  got: Extraction | null; decision: string; reasons: string[]; status: Status; error: string | null; ms: number; fields: Record<string, boolean | null>
}
interface Run { id: string; label: string; model?: string; when?: string; note?: string; cases: Record<string, Case> }
type Stats = ReturnType<typeof stats>

const FIELDS = ['lr_no', 'stamp', 'signature', 'date', 'quantity', 'items', 'total', 'remarks', 'shortage_flag'] as const
const DECISIONS = ['verified', 'needs_review', 'retake_requested'] as const
const STATUS: Record<Status, { icon: LucideIcon; cls: string; key: Key }> = {
  pass: { icon: CircleCheck, cls: 'bg-ok-soft text-ok', key: 'bench.s.pass' },
  unsafe: { icon: XCircle, cls: 'bg-bad-soft text-bad', key: 'bench.s.unsafe' },
  friction: { icon: TriangleAlert, cls: 'bg-warn-soft text-warn', key: 'bench.s.friction' },
  different: { icon: ArrowLeftRight, cls: 'bg-accent-soft text-accent', key: 'bench.s.different' },
  error: { icon: TriangleAlert, cls: 'bg-wash text-muted', key: 'bench.s.error' },
}

const pct = (n: number, d: number) => (d ? Math.round((1000 * n) / d) / 10 : null)
const fmtPct = (p: number | null) => (p === null ? '–' : `${p}%`)
const secs = (ms: number) => `${(ms / 1000).toFixed(1)} s`
const median = (a: number[]) => { if (!a.length) return 0; const s = [...a].sort((x, y) => x - y); const h = s.length >> 1; return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2 }
const order = (c: Case) => `${c.sheet}${c.cond === 'flat' ? '' : `_${c.cond}`}`

function stats(run: Run) {
  const cs = Object.values(run.cases).sort((a, b) => order(a).localeCompare(order(b)))
  const count = (s: Status) => cs.filter((c) => c.status === s).length
  const fields = Object.fromEntries(FIELDS.map((f) => {
    const a = cs.filter((c) => c.fields[f] !== null && c.fields[f] !== undefined)
    return [f, { ok: a.filter((c) => c.fields[f]).length, n: a.length }]
  })) as Record<(typeof FIELDS)[number], { ok: number; n: number }>
  const tags: Record<string, { ok: number; n: number }> = {}
  cs.forEach((c) => c.tags.forEach((t) => { const x = (tags[t] ??= { ok: 0, n: 0 }); x.n++; if (c.status === 'pass') x.ok++ }))
  const matrix: Record<string, number> = {}
  cs.forEach((c) => { const k = `${c.expected.decision}>${c.decision}`; matrix[k] = (matrix[k] ?? 0) + 1 })
  const fieldOk = Object.values(fields).reduce((n, f) => n + f.ok, 0)
  const fieldN = Object.values(fields).reduce((n, f) => n + f.n, 0)
  const lat = cs.filter((c) => !c.error).map((c) => c.ms).sort((a, b) => a - b)
  return {
    cs, n: cs.length, pass: count('pass'), unsafe: count('unsafe'), friction: count('friction'), different: count('different'), error: count('error'),
    good: cs.filter((c) => c.expected.decision === 'verified' && c.expected.accept.includes('verified')).length,
    fields, fieldOk, fieldN, tags, matrix, median: median(lat), p95: lat[Math.min(lat.length - 1, Math.floor(lat.length * 0.95))] ?? 0, total: cs.reduce((n, c) => n + c.ms, 0),
    passPct: pct(count('pass'), cs.length), fieldPct: pct(fieldOk, fieldN),
  }
}

const photoCache = new Map<string, string>() // object URLs, kept so switching runs does not download the photos again
function usePhoto(name: string): string | null {
  const [url, setUrl] = useState<string | null>(photoCache.get(name) ?? null)
  useEffect(() => {
    if (photoCache.has(name)) { setUrl(photoCache.get(name)!); return }
    let alive = true
    fetchBlob(`/benchmark/photos/${name}`).then((b) => { const u = URL.createObjectURL(b); photoCache.set(name, u); if (alive) setUrl(u) }).catch(() => undefined)
    return () => { alive = false }
  }, [name])
  return url
}

function Thumb({ name, label, onOpen }: { name: string; label: string; onOpen: (url: string) => void }) {
  const url = usePhoto(name)
  return url
    ? <button type="button" onClick={() => onOpen(url)} aria-label={label} className="shrink-0"><img src={url} alt={label} className="h-32 w-24 rounded-lg border border-line object-cover object-top" /></button>
    : <div className="h-32 w-24 shrink-0 animate-pulse rounded-lg border border-line bg-wash" aria-hidden />
}

/** A change against the compared run: green when it moved the right way. `lowerIsBetter` for counts of problems and for time. */
function Delta({ now, before, unit = '', lowerIsBetter = false, digits = 0 }: { now: number | null; before: number | null | undefined; unit?: string; lowerIsBetter?: boolean; digits?: number }) {
  if (now === null || before === null || before === undefined) return null
  const d = Math.round((now - before) * 10 ** digits) / 10 ** digits
  if (d === 0) return <span className="text-xs text-muted">±0</span>
  const good = lowerIsBetter ? d < 0 : d > 0
  return <span className={`text-xs font-medium tabular-nums ${good ? 'text-ok' : 'text-bad'}`}>{d > 0 ? '▲ +' : '▼ '}{d}{unit}</span>
}

function Bar({ label, ok, n, before }: { label: string; ok: number; n: number; before?: { ok: number; n: number } }) {
  const { t } = useI18n()
  const p = pct(ok, n)
  const tone = p === null ? 'bg-line' : p < 60 ? 'bg-bad' : p < 85 ? 'bg-warn' : 'bg-accent'
  return (
    <div className="grid grid-cols-[8.5rem_1fr_9.5rem] items-center gap-3 py-1.5 text-sm">
      <span className="truncate" title={label}>{label}</span>
      <div className="h-2.5 overflow-hidden rounded-full bg-wash" role="img" aria-label={`${label}: ${fmtPct(p)}`}><div className={`h-full rounded-full ${tone}`} style={{ width: `${p ?? 0}%` }} /></div>
      <span className="flex items-center justify-end gap-1.5 text-right tabular-nums text-muted">
        {fmtPct(p)} <span className="text-xs">({ok}/{n})</span>
        {before && <Delta now={p} before={pct(before.ok, before.n)} unit={t('bench.pp')} digits={0} />}
      </span>
    </div>
  )
}

function Card({ title, children }: { title?: string; children: ReactNode }) {
  return <section className="rounded-2xl border border-line bg-surface p-5">{title && <h2 className="mb-3 text-sm font-semibold">{title}</h2>}{children}</section>
}

function Kpi({ label, value, note, tone = '', delta }: { label: string; value: string | number; note: string; tone?: string; delta?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-1 whitespace-nowrap text-3xl font-semibold tabular-nums ${tone}`}>{value}</div>
      <div className="min-h-4 whitespace-nowrap">{delta}</div>
      <div className="mt-1 text-xs text-muted">{note}</div>
    </div>
  )
}

const Chip = ({ children, cls = 'bg-wash text-muted' }: { children: ReactNode; cls?: string }) => <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>{children}</span>

export default function Benchmark() {
  const { t } = useI18n()
  const [runs, setRuns] = useState<Run[] | null>(null)
  const [error, setError] = useState(false)
  const [pick, setPick] = useState<string | null>(null)
  const [base, setBase] = useState<string | null | undefined>(undefined) // undefined: the run before this one
  const [tab, setTab] = useState<'overview' | 'photos'>('overview')
  const [filter, setFilter] = useState<'all' | 'bad' | Status>('all')
  const [kind, setKind] = useState('')
  const [q, setQ] = useState('')
  const [zoom, setZoom] = useState<string | null>(null)

  useEffect(() => { api<Run[]>('/benchmark/runs').then((r) => { setRuns(r); setPick(r.at(-1)?.id ?? null) }).catch(() => setError(true)) }, [])
  const all = useMemo(() => (runs ?? []).map((r) => ({ run: r, s: stats(r) })), [runs])

  if (error) return <p className="text-bad">{t('bench.error')}</p>
  if (!runs) return <p className="text-muted">{t('common.loading')}</p>
  const head = (
    <div>
      <h1 className="text-3xl font-semibold tracking-tight">{t('bench.title')}</h1>
      <p className="text-sm text-muted">{t('bench.sub')}</p>
    </div>
  )
  if (!runs.length) return <div className="space-y-6">{head}<p className="rounded-2xl border border-line px-4 py-12 text-center text-muted">{t('bench.empty')}</p></div>

  const idx = Math.max(0, all.findIndex((x) => x.run.id === pick))
  const { run, s } = all[idx]
  const prev = base === undefined ? all[idx - 1] : all.find((x) => x.run.id === base)
  const b: Stats | undefined = prev?.s
  const bestId = [...all].sort((x, y) => x.s.unsafe - y.s.unsafe || (y.s.passPct ?? 0) - (x.s.passPct ?? 0))[0].run.id
  const choose = (id: string) => { setPick(id); setBase(undefined); setFilter('all'); setKind(''); setQ('') }

  const kinds = [...new Set(s.cs.flatMap((c) => c.tags))].sort()
  const rows = s.cs.filter((c) => (filter === 'all' || (filter === 'bad' ? c.status !== 'pass' : c.status === filter)) && (!kind || c.tags.includes(kind))
    && (!q || `${c.sheet} ${c.title} ${c.do} ${c.tags.join(' ')}`.toLowerCase().includes(q.toLowerCase())))
  const chips: [typeof filter, string, number][] = [['all', t('bench.f.all'), s.n], ['bad', t('bench.f.bad'), s.n - s.pass], ['pass', t('bench.s.pass'), s.pass], ['unsafe', t('bench.s.unsafe'), s.unsafe], ['friction', t('bench.s.friction'), s.friction], ['different', t('bench.s.different'), s.different]]
  const decName = (d: string) => (d === 'verified' ? t('bench.d.verify') : d === 'needs_review' ? t('bench.d.review') : t('bench.d.retake'))
  const was = (c: Case): Status | null => { const o = prev?.run.cases[Object.keys(run.cases).find((k) => run.cases[k] === c) ?? '']; return o && o.status !== c.status ? o.status : null }
  const changed = s.cs.map((c) => ({ c, was: was(c) })).filter((x) => x.was)
  const rank: Record<Status, number> = { pass: 0, friction: 1, different: 1, error: 2, unsafe: 3 }

  return (
    <div className="space-y-6">
      {head}
      <div className="grid gap-6 lg:grid-cols-[17rem_minmax(0,1fr)]">
        {/* the runs, newest first */}
        <aside aria-label={t('bench.runsTitle')} className="lg:sticky lg:top-20 lg:self-start">
          <label className="block lg:hidden">
            <span className="text-xs font-medium uppercase tracking-wide text-muted">{t('bench.runsTitle')}</span>
            <select value={run.id} onChange={(e) => choose(e.target.value)} className="mt-1 h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm">
              {[...all].reverse().map(({ run: r }) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
          </label>
          <div className="hidden lg:block">
            <div className="mb-2 flex items-baseline justify-between px-1"><h2 className="text-sm font-semibold">{t('bench.runsTitle')}</h2><span className="text-xs text-muted">{all.length}</span></div>
            <ul className="space-y-2">
              {[...all].reverse().map(({ run: r, s: x }) => (
                <li key={r.id}>
                  <button type="button" onClick={() => choose(r.id)} aria-pressed={r.id === run.id}
                    className={`w-full rounded-xl border p-3 text-left ${r.id === run.id ? 'border-ink bg-surface shadow-sm' : 'border-line bg-surface/60 hover:bg-surface'}`}>
                    <div className="text-sm font-medium leading-snug">{r.label}</div>
                    <div className="mt-0.5 truncate text-xs text-muted">{r.model}</div>
                    <div className="text-xs text-muted">{r.when}</div>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <Chip cls="bg-wash text-ink">{fmtPct(x.passPct)}</Chip>
                      <Chip cls={x.unsafe ? 'bg-bad-soft text-bad' : 'bg-ok-soft text-ok'}>{t('bench.run.unsafeShort', { n: x.unsafe })}</Chip>
                      {r.id === bestId && all.length > 1 && <Chip cls="bg-accent-soft text-accent">{t('bench.best')}</Chip>}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
            <p className="mt-3 px-1 text-xs text-muted">{t('bench.sideNote')}</p>
          </div>
        </aside>

        <div className="min-w-0 space-y-5">
          <Card>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="text-xl font-semibold tracking-tight">{run.label}</h2>
                <p className="text-sm text-muted">{run.model} · {run.when} · {s.n} {t('bench.run.photos').toLowerCase()} · {secs(s.total)}</p>
                {run.note && <p className="mt-1 text-sm text-muted">{run.note}</p>}
              </div>
              {all.length > 1 && (
                <label className="text-sm">
                  <span className="mr-2 text-muted">{t('bench.compareWith')}</span>
                  <select value={base === undefined ? (prev?.run.id ?? '') : (base ?? '')} onChange={(e) => setBase(e.target.value || null)} className="h-9 rounded-lg border border-line bg-surface px-2 text-sm">
                    <option value="">{t('bench.compareNone')}</option>
                    {all.filter((x) => x.run.id !== run.id).map((x) => <option key={x.run.id} value={x.run.id}>{x.run.label}</option>)}
                  </select>
                </label>
              )}
            </div>
            <div role="tablist" className="mt-4 flex gap-6 border-b border-line">
              {([['overview', t('bench.tab.overview')], ['photos', `${t('bench.tab.photos')} (${s.n})`]] as const).map(([k, label]) => (
                <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                  className={`-mb-px border-b-2 px-1 pb-2 text-sm font-medium ${tab === k ? 'border-ink text-ink' : 'border-transparent text-muted hover:text-ink'}`}>{label}</button>
              ))}
            </div>
          </Card>

          {tab === 'overview' && (
            <>
              <div className={`flex items-start gap-3 rounded-2xl px-5 py-4 text-sm font-medium ${s.unsafe ? 'bg-bad-soft text-bad' : 'bg-ok-soft text-ok'}`} role="status">
                {s.unsafe ? <XCircle size={18} className="mt-0.5 shrink-0" aria-hidden /> : <CircleCheck size={18} className="mt-0.5 shrink-0" aria-hidden />}
                {s.unsafe ? t('bench.unsafeN', { n: s.unsafe }) : t('bench.unsafe0')}
              </div>

              <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
                <Kpi label={t('bench.k.pass')} value={fmtPct(s.passPct)} note={t('bench.k.passNote', { a: s.pass, b: s.n })} tone={s.pass / s.n >= 0.85 ? 'text-ok' : 'text-warn'} delta={b && <Delta now={s.passPct} before={b.passPct} unit={t('bench.pp')} digits={1} />} />
                <Kpi label={t('bench.k.unsafe')} value={s.unsafe} note={t('bench.k.unsafeNote')} tone={s.unsafe ? 'text-bad' : 'text-ok'} delta={b && <Delta now={s.unsafe} before={b.unsafe} lowerIsBetter />} />
                <Kpi label={t('bench.k.needless')} value={s.friction} note={t('bench.k.needlessNote', { n: s.good })} tone={s.friction ? 'text-warn' : 'text-ok'} delta={b && <Delta now={s.friction} before={b.friction} lowerIsBetter />} />
                <Kpi label={t('bench.k.fields')} value={fmtPct(s.fieldPct)} note={t('bench.k.fieldsNote', { a: s.fieldOk, b: s.fieldN })} tone={(s.fieldPct ?? 0) >= 85 ? 'text-ok' : 'text-warn'} delta={b && <Delta now={s.fieldPct} before={b.fieldPct} unit={t('bench.pp')} digits={1} />} />
                <Kpi label={t('bench.k.time')} value={secs(s.median)} note={t('bench.k.timeNote', { t: secs(s.p95) })} delta={b && <Delta now={s.median / 1000} before={b.median / 1000} unit=" s" lowerIsBetter digits={1} />} />
              </div>

              {prev && (
                <Card title={t('bench.changedTitle', { name: prev.run.label })}>
                  {changed.length === 0 ? <p className="text-sm text-muted">{t('bench.changedNone')}</p> : (
                    <ul className="divide-y divide-line">
                      {changed.map(({ c, was: w }) => {
                        const better = rank[c.status] < rank[w!]
                        return (
                          <li key={order(c)} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                            <Chip cls={better ? 'bg-ok-soft text-ok' : c.status === 'pass' ? 'bg-ok-soft text-ok' : 'bg-bad-soft text-bad'}>{better ? t('bench.fixed') : t('bench.broke')}</Chip>
                            <span className="font-mono font-medium">{c.sheet}{c.cond !== 'flat' ? ` · ${c.cond}` : ''}</span>
                            <span className="min-w-0 flex-1 truncate text-muted">{c.title}</span>
                            <Chip cls={STATUS[w!].cls}>{t(STATUS[w!].key)}</Chip><ArrowRight size={14} className="text-muted" aria-hidden /><Chip cls={STATUS[c.status].cls}>{t(STATUS[c.status].key)}</Chip>
                            <button type="button" onClick={() => { setTab('photos'); setFilter('all'); setKind(''); setQ(c.sheet) }} className="text-accent underline-offset-2 hover:underline">{t('bench.openPhoto')}</button>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </Card>
              )}

              <div className="grid gap-4 xl:grid-cols-2">
                <Card title={t('bench.fields')}>{FIELDS.map((f) => s.fields[f].n > 0 && <Bar key={f} label={t(`bench.field.${f}` as Key)} ok={s.fields[f].ok} n={s.fields[f].n} before={b?.fields[f]} />)}</Card>
                <Card title={t('bench.kinds')}>{Object.entries(s.tags).sort().map(([k, v]) => <Bar key={k} label={k} ok={v.ok} n={v.n} before={b?.tags[k]} />)}</Card>
              </div>

              <Card title={t('bench.matrix')}>
                <table className="w-full text-sm">
                  <thead className="text-xs uppercase tracking-wide text-muted"><tr><th className="py-1.5 text-left font-medium">{t('bench.expected')} ↓ · {t('bench.got')} →</th>{DECISIONS.map((d) => <th key={d} className="text-right font-medium">{decName(d)}</th>)}</tr></thead>
                  <tbody>{DECISIONS.map((e) => (
                    <tr key={e} className="border-t border-line"><td className="py-2 font-medium">{decName(e)}</td>
                      {DECISIONS.map((g) => { const v = s.matrix[`${e}>${g}`] ?? 0; const bad = v > 0 && g === 'verified' && e !== 'verified'; return <td key={g} className={`text-right tabular-nums ${bad ? 'font-semibold text-bad' : v ? '' : 'text-muted'}`}>{v || '·'}</td> })}
                    </tr>))}
                  </tbody>
                </table>
                <p className="mt-3 text-xs text-muted">{t('bench.matrixNote')}</p>
              </Card>

              <details className="rounded-2xl border border-line p-5 text-sm text-muted">
                <summary className="cursor-pointer font-medium text-ink">{t('bench.howTitle')}</summary>
                <p className="mt-3">{t('bench.how')}</p>
                <p className="mt-2">{t('bench.add')}</p>
              </details>
            </>
          )}

          {tab === 'photos' && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2" role="search">
                {chips.map(([k, label, n]) => (
                  <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)}
                    className={`h-9 rounded-full border px-3.5 text-sm ${filter === k ? 'border-ink bg-ink text-surface' : 'border-line bg-surface text-muted hover:text-ink'}`}>{label} <span className="tabular-nums opacity-70">{n}</span></button>
                ))}
                <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label={t('bench.kindLabel')} className="h-9 rounded-lg border border-line bg-surface px-3 text-sm">
                  <option value="">{t('bench.kindAll')}</option>{kinds.map((k) => <option key={k}>{k}</option>)}
                </select>
                <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('bench.search')} aria-label={t('filter.search')} className="h-9 min-w-48 rounded-lg border border-line bg-surface px-3 text-sm" />
              </div>
              {rows.length === 0 && <p className="rounded-xl border border-line px-4 py-8 text-center text-muted">{t('filter.none')}</p>}
              <ul className="space-y-3">{rows.map((c) => <CaseRow key={order(c)} c={c} was={was(c)} wasLabel={prev?.run.label} decName={decName} onOpen={setZoom} />)}</ul>
            </div>
          )}
        </div>
      </div>

      {zoom && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/80 p-4" role="dialog" aria-modal="true" onClick={() => setZoom(null)}>
          <button type="button" aria-label={t('setup.close')} className="absolute right-4 top-4 grid h-10 w-10 place-items-center rounded-full bg-surface text-ink"><X size={18} aria-hidden /></button>
          <img src={zoom} alt="" className="max-h-full max-w-full rounded-lg" />
        </div>
      )}
    </div>
  )
}

function CaseRow({ c, was, wasLabel, decName, onOpen }: { c: Case; was: Status | null; wasLabel?: string; decName: (d: string) => string; onOpen: (url: string) => void }) {
  const { t } = useI18n()
  const st = STATUS[c.status]
  const g = c.got
  const e = c.expected
  const yn = (b: boolean | undefined) => (b ? t('bench.present') : t('bench.absent'))
  const items = (g?.items ?? []).map((i) => `${i.name ?? ''} ${i.quantity ?? '?'} ${i.unit ?? ''}`.trim()).join('; ')
  const line = (label: string, want: string, got: string, ok: boolean | null | undefined) => (
    <tr key={label} className="border-t border-line"><td className="py-1.5 pr-3 text-muted">{label}</td><td className="pr-3">{want}</td>
      <td className={ok === false ? 'font-semibold text-bad' : ok ? 'text-ok' : ''}>{got}</td></tr>
  )
  return (
    <li className="flex gap-4 rounded-2xl border border-line bg-surface p-4">
      <Thumb name={c.photo} label={`${c.sheet} ${c.title}`} onOpen={onOpen} />
      <div className="min-w-0 flex-1 space-y-2">
        <div>
          <h3 className="font-semibold"><span className="font-mono">{c.sheet}{c.cond !== 'flat' ? ` · ${c.cond}` : ''}</span> · {c.title}</h3>
          <p className="text-sm text-muted">{t('bench.written')}: {c.do}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-sm">
          <Chip cls={st.cls}><st.icon size={13} aria-hidden /> {t(st.key)}</Chip>
          {was && <span className="text-xs text-muted" title={wasLabel}>{t('bench.wasLabel')} {t(STATUS[was].key)}</span>}
          <span className="text-xs text-muted">{t('bench.expected')}</span><Chip>{e.accept.length > 1 ? e.accept.map(decName).join(' / ') : decName(e.decision)}</Chip>
          <span className="text-xs text-muted">{t('bench.got')}</span><Chip cls={c.status === 'unsafe' ? 'bg-bad-soft text-bad' : undefined}>{decName(c.decision)}</Chip>
          <span className="text-xs text-muted">{secs(c.ms)}</span>
          {c.judgement && <Chip>{t('bench.judgement')}</Chip>}
        </div>
        {c.reasons.length > 0 && <ReasonChips reasons={c.reasons} />}
        <div className="flex flex-wrap gap-1.5">{c.tags.map((k) => <Chip key={k}>#{k}</Chip>)}</div>
        <div className="flex flex-wrap gap-1">
          {FIELDS.map((f) => { const v = c.fields[f]; return v === null || v === undefined ? null : <span key={f} className={`rounded-md px-1.5 py-0.5 text-[11px] ${v ? 'bg-ok-soft text-ok' : 'bg-bad-soft text-bad'}`}>{v ? '✓' : '✕'} {t(`bench.field.${f}` as Key)}</span> })}
        </div>
        <details className="text-sm">
          <summary className="cursor-pointer text-accent">{t('bench.details')}</summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[28rem] text-left text-xs">
              <thead className="text-muted"><tr><th className="pb-1 font-medium" /><th className="font-medium">{t('bench.expected')}</th><th className="font-medium">{t('bench.read')}</th></tr></thead>
              <tbody>
                {line(t('bench.field.lr_no'), e.lr, g?.lr_no ?? '–', c.fields.lr_no)}
                {line(t('bench.field.stamp'), yn(e.stamp), yn(g?.consignee_stamp_present), c.fields.stamp)}
                {line(t('bench.field.signature'), yn(e.signature), yn(g?.signature_present), c.fields.signature)}
                {line(t('bench.field.date'), e.date ?? t('bench.blank'), g?.delivery_date ?? t('bench.blank'), c.fields.date)}
                {line(t('bench.field.quantity'), e.quantity || t('bench.blank'), g?.quantity_received ?? t('bench.blank'), c.fields.quantity)}
                {e.items.length > 0 && line(t('bench.field.items'), e.items.join(', '), items || '–', c.fields.items)}
                {e.total !== null && line(t('bench.field.total'), String(e.total), g?.total_quantity ?? '–', c.fields.total)}
                {line(t('bench.field.remarks'), e.remarks || t('bench.none'), g?.remarks || t('bench.none'), c.fields.remarks)}
                {line(t('bench.field.shortage_flag'), '', g?.shortage_or_damage ? t('bench.yes') : t('bench.no'), c.fields.shortage_flag)}
                <tr className="border-t border-line"><td className="py-1.5 pr-3 text-muted">{t('bench.confidence')}</td><td /><td>{g ? `${g.confidence}${g.issues.length ? ` · ${g.issues.join(', ')}` : ''}` : '–'}</td></tr>
                {c.error && <tr className="border-t border-line"><td className="py-1.5 pr-3 text-muted">{t('bench.s.error')}</td><td /><td className="text-bad">{c.error}</td></tr>}
              </tbody>
            </table>
          </div>
        </details>
      </div>
    </li>
  )
}
