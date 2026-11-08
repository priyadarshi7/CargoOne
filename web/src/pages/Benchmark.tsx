import { ArrowLeftRight, CircleCheck, TriangleAlert, X, XCircle, type LucideIcon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
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
    fields, fieldOk, fieldN, tags, matrix, median: median(lat), p95: lat[Math.min(lat.length - 1, Math.floor(lat.length * 0.95))] ?? 0,
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

function Bar({ label, ok, n }: { label: string; ok: number; n: number }) {
  const p = pct(ok, n)
  const tone = p === null ? 'bg-line' : p < 60 ? 'bg-bad' : p < 85 ? 'bg-warn' : 'bg-accent'
  return (
    <div className="grid grid-cols-[9rem_1fr_6.5rem] items-center gap-3 py-1.5 text-sm">
      <span className="truncate" title={label}>{label}</span>
      <div className="h-2.5 overflow-hidden rounded-full bg-wash" role="img" aria-label={`${label}: ${fmtPct(p)}`}><div className={`h-full rounded-full ${tone}`} style={{ width: `${p ?? 0}%` }} /></div>
      <span className="text-right tabular-nums text-muted">{fmtPct(p)} <span className="text-xs">({ok}/{n})</span></span>
    </div>
  )
}

function Card({ title, children }: { title?: string; children: React.ReactNode }) {
  return <section className="rounded-2xl border border-line bg-surface p-5">{title && <h2 className="mb-3 text-sm font-semibold">{title}</h2>}{children}</section>
}

function Kpi({ label, value, note, tone = '' }: { label: string; value: string | number; note: string; tone?: string }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-1 text-3xl font-semibold tabular-nums ${tone}`}>{value}</div>
      <div className="text-xs text-muted">{note}</div>
    </div>
  )
}

const Chip = ({ children, cls = 'bg-wash text-muted' }: { children: React.ReactNode; cls?: string }) => <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>{children}</span>

export default function Benchmark() {
  const { t } = useI18n()
  const [runs, setRuns] = useState<Run[] | null>(null)
  const [error, setError] = useState(false)
  const [pick, setPick] = useState<string | null>(null)
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

  const cur = all.find((x) => x.run.id === pick) ?? all[all.length - 1]
  const { run, s } = cur
  const kinds = [...new Set(s.cs.flatMap((c) => c.tags))].sort()
  const rows = s.cs.filter((c) => (filter === 'all' || (filter === 'bad' ? c.status !== 'pass' : c.status === filter)) && (!kind || c.tags.includes(kind))
    && (!q || `${c.sheet} ${c.title} ${c.do} ${c.tags.join(' ')}`.toLowerCase().includes(q.toLowerCase())))
  const chips: [typeof filter, string, number][] = [['all', t('bench.f.all'), s.n], ['bad', t('bench.f.bad'), s.n - s.pass], ['pass', t('bench.s.pass'), s.pass], ['unsafe', t('bench.s.unsafe'), s.unsafe], ['friction', t('bench.s.friction'), s.friction], ['different', t('bench.s.different'), s.different]]
  const decName = (d: string) => (d === 'verified' ? t('bench.d.verify') : d === 'needs_review' ? t('bench.d.review') : t('bench.d.retake'))
  const fieldPct = pct(s.fieldOk, s.fieldN)

  return (
    <div className="space-y-6">
      {head}

      <Card title={t('bench.runs')}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted"><tr>
              <th className="py-2 font-medium">{t('bench.c.run')}</th><th className="font-medium">{t('bench.c.model')}</th><th className="text-right font-medium">{t('bench.c.pass')}</th>
              <th className="text-right font-medium">{t('bench.c.unsafe')}</th><th className="text-right font-medium">{t('bench.c.needless')}</th><th className="text-right font-medium">{t('bench.c.fields')}</th><th className="text-right font-medium">{t('bench.c.time')}</th>
            </tr></thead>
            <tbody>{[...all].reverse().map(({ run: r, s: x }) => (
              <tr key={r.id} className={`border-t border-line ${r.id === run.id ? 'bg-accent-soft' : ''}`}>
                <td className="py-2.5 pr-3"><button type="button" onClick={() => setPick(r.id)} aria-pressed={r.id === run.id} className="text-left font-medium hover:underline">{r.label}</button><div className="text-xs text-muted">{r.when}</div></td>
                <td className="pr-3 text-muted">{r.model}</td>
                <td className="text-right tabular-nums">{fmtPct(pct(x.pass, x.n))}</td>
                <td className={`text-right font-semibold tabular-nums ${x.unsafe ? 'text-bad' : 'text-ok'}`}>{x.unsafe}</td>
                <td className="text-right tabular-nums">{x.friction}</td>
                <td className="text-right tabular-nums">{fmtPct(pct(x.fieldOk, x.fieldN))}</td>
                <td className="text-right tabular-nums text-muted">{secs(x.median)}</td>
              </tr>))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className={`flex items-start gap-3 rounded-2xl px-5 py-4 text-sm font-medium ${s.unsafe ? 'bg-bad-soft text-bad' : 'bg-ok-soft text-ok'}`} role="status">
        {s.unsafe ? <XCircle size={18} className="mt-0.5 shrink-0" aria-hidden /> : <CircleCheck size={18} className="mt-0.5 shrink-0" aria-hidden />}
        <div>
          <div>{s.unsafe ? t('bench.unsafeN', { n: s.unsafe }) : t('bench.unsafe0')}</div>
          <div className="mt-0.5 font-normal opacity-90">{run.label}{run.note ? `: ${run.note}` : ''}</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Kpi label={t('bench.k.pass')} value={fmtPct(pct(s.pass, s.n))} note={t('bench.k.passNote', { a: s.pass, b: s.n })} tone={s.pass / s.n >= 0.85 ? 'text-ok' : 'text-warn'} />
        <Kpi label={t('bench.k.unsafe')} value={s.unsafe} note={t('bench.k.unsafeNote')} tone={s.unsafe ? 'text-bad' : 'text-ok'} />
        <Kpi label={t('bench.k.needless')} value={s.friction} note={t('bench.k.needlessNote', { n: s.good })} tone={s.friction ? 'text-warn' : 'text-ok'} />
        <Kpi label={t('bench.k.fields')} value={fmtPct(fieldPct)} note={t('bench.k.fieldsNote', { a: s.fieldOk, b: s.fieldN })} tone={(fieldPct ?? 0) >= 85 ? 'text-ok' : 'text-warn'} />
        <Kpi label={t('bench.k.time')} value={secs(s.median)} note={t('bench.k.timeNote', { t: secs(s.p95) })} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={t('bench.fields')}>{FIELDS.map((f) => s.fields[f].n > 0 && <Bar key={f} label={t(`bench.field.${f}` as Key)} ok={s.fields[f].ok} n={s.fields[f].n} />)}</Card>
        <Card title={t('bench.kinds')}>{Object.entries(s.tags).sort().map(([k, v]) => <Bar key={k} label={k} ok={v.ok} n={v.n} />)}</Card>
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

      <div className="space-y-3">
        <h2 className="text-lg font-semibold">{t('bench.suite')}</h2>
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
        <ul className="space-y-3">{rows.map((c) => <CaseRow key={order(c)} c={c} decName={decName} onOpen={setZoom} />)}</ul>
      </div>

      <details className="rounded-2xl border border-line p-5 text-sm text-muted">
        <summary className="cursor-pointer font-medium text-ink">{t('bench.howTitle')}</summary>
        <p className="mt-3">{t('bench.how')}</p>
        <p className="mt-2">{t('bench.add')}</p>
      </details>

      {zoom && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/80 p-4" role="dialog" aria-modal="true" onClick={() => setZoom(null)}>
          <button type="button" aria-label={t('setup.close')} className="absolute right-4 top-4 grid h-10 w-10 place-items-center rounded-full bg-surface text-ink"><X size={18} aria-hidden /></button>
          <img src={zoom} alt="" className="max-h-full max-w-full rounded-lg" />
        </div>
      )}
    </div>
  )
}

function CaseRow({ c, decName, onOpen }: { c: Case; decName: (d: string) => string; onOpen: (url: string) => void }) {
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
