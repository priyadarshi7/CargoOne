import { useState } from 'react'

/** Ordinal sequential ramp (one hue, light -> dark), validated step range from the dataviz palette:
 *  the lightest step is no lighter than step 250 so every segment stays visible on white. */
export const AGE_RAMP = ['#86b6ef', '#3987e5', '#1c5cab', '#0d366b']

interface Bucket { label: string; count: number }

/** Horizontal stacked bars, one row per branch. 2 px surface gap between segments; counts printed inside
 *  segments that are wide enough; legend always present; exact numbers also available as a table. */
export function StackedBars({ rows }: { rows: { name: string; buckets: Bucket[] }[] }) {
  const labels = rows[0]?.buckets.map((b) => b.label) ?? []
  const max = Math.max(1, ...rows.map((r) => r.buckets.reduce((n, b) => n + b.count, 0)))
  return (
    <div>
      <ul className="mb-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted" aria-label="Legend">
        {labels.map((l, i) => (
          <li key={l} className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: AGE_RAMP[i] }} /> {l}
          </li>
        ))}
      </ul>
      <div className="space-y-3">
        {rows.map((r) => {
          const total = r.buckets.reduce((n, b) => n + b.count, 0)
          return (
            <div key={r.name} className="grid grid-cols-[8rem_1fr_2rem] items-center gap-3 text-sm">
              <span className="truncate text-muted" title={r.name}>{r.name}</span>
              <div className="flex h-6 gap-0.5" role="img" aria-label={`${r.name}: ${total} missing PODs`}>
                {r.buckets.map((b, i) => b.count > 0 && (
                  <div key={b.label} title={`${r.name} · ${b.label}: ${b.count}`}
                    className="grid min-w-[4px] place-items-center text-[11px] font-medium text-white first:rounded-l last:rounded-r"
                    style={{ width: `${(b.count / max) * 100}%`, background: AGE_RAMP[i], color: i === 0 ? '#0b0b0b' : '#fff' }}>
                    {(b.count / max) > 0.07 ? b.count : ''}
                  </div>
                ))}
              </div>
              <span className="text-right font-medium tabular-nums">{total}</span>
            </div>
          )
        })}
      </div>
      <details className="mt-4 text-xs text-muted">
        <summary className="cursor-pointer">View as table</summary>
        <table className="mt-2 w-full text-left">
          <thead><tr><th className="py-1 font-medium">Branch</th>{labels.map((l) => <th key={l} className="py-1 font-medium">{l}</th>)}</tr></thead>
          <tbody>{rows.map((r) => <tr key={r.name} className="border-t border-line"><td className="py-1">{r.name}</td>{r.buckets.map((b) => <td key={b.label} className="py-1 tabular-nums">{b.count}</td>)}</tr>)}</tbody>
        </table>
      </details>
    </div>
  )
}

interface Point { label: string; value: number | null }

/** Single-series line chart with a dashed target line, crosshair + readout on hover, and a table fallback.
 *  Gaps (no data that week) break the line instead of drawing a false zero. */
export function LineChart({ points, target, max, unit, targetLabel, fmt = (v: number) => String(v) }: {
  points: Point[]; target: number; max: number; unit: string; targetLabel: string; fmt?: (v: number) => string
}) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 480, H = 170, L = 34, R = 12, T = 12, B = 26
  const x = (i: number) => L + (points.length === 1 ? 0 : (i / (points.length - 1)) * (W - L - R))
  const y = (v: number) => T + (1 - Math.min(v, max) / max) * (H - T - B)
  const segs: string[] = []
  let cur = ''
  points.forEach((p, i) => {
    if (p.value === null) { if (cur) segs.push(cur); cur = ''; return }
    cur += `${cur ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`
  })
  if (cur) segs.push(cur)

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - r.left) / r.width) * W
    setHover(Math.max(0, Math.min(points.length - 1, Math.round(((px - L) / (W - L - R)) * (points.length - 1)))))
  }
  const hp = hover !== null ? points[hover] : null

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`${unit} by week, target ${fmt(target)}`}
        onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {[0, max / 2, max].map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="#e2e8f0" strokeWidth="1" />
            <text x={L - 6} y={y(v) + 3} textAnchor="end" fontSize="10" fill="#898781">{fmt(v)}</text>
          </g>
        ))}
        <line x1={L} x2={W - R} y1={y(target)} y2={y(target)} stroke="#15803d" strokeWidth="1.5" strokeDasharray="4 4" />
        <text x={W - R} y={y(target) - 4} textAnchor="end" fontSize="10" fill="#15803d">{targetLabel}</text>
        {segs.map((d, i) => <path key={i} d={d} fill="none" stroke="#2a78d6" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />)}
        {points.map((p, i) => p.value !== null && (
          <circle key={i} cx={x(i)} cy={y(p.value)} r={hover === i ? 5 : 3.5} fill="#2a78d6" stroke="#fff" strokeWidth="2" />
        ))}
        {points.map((p, i) => (i % 2 === 0 || points.length < 6) && (
          <text key={p.label} x={x(i)} y={H - 8} textAnchor="middle" fontSize="10" fill="#898781">{p.label}</text>
        ))}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke="#64748b" strokeWidth="1" />}
      </svg>
      <p className="h-5 text-xs text-muted" aria-live="polite">
        {hp ? <>Week of <b className="text-ink">{hp.label}</b>: {hp.value === null ? 'no data' : <b className="text-ink">{fmt(hp.value)}</b>}</> : ' '}
      </p>
      <details className="text-xs text-muted">
        <summary className="cursor-pointer">View as table</summary>
        <table className="mt-2 w-full text-left"><tbody>
          {points.map((p) => <tr key={p.label} className="border-t border-line"><td className="py-1">{p.label}</td><td className="py-1 tabular-nums">{p.value === null ? '—' : fmt(p.value)}</td></tr>)}
        </tbody></table>
      </details>
    </div>
  )
}
