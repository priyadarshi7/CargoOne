import { useEffect, useState } from 'react'
import { useI18n } from '../lib/i18n'

/** True when the device asks for less motion: the route is then drawn complete and the truck stays still. */
function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches)
  useEffect(() => {
    if (typeof matchMedia !== 'function') return
    const q = matchMedia('(prefers-reduced-motion: reduce)')
    const on = () => setReduced(q.matches)
    q.addEventListener('change', on)
    return () => q.removeEventListener('change', on)
  }, [])
  return reduced
}

const PATH = 'M 110 238 C 290 70, 520 300, 690 150 S 870 96, 890 96'

/**
 * The landing hero picture: a quiet dot grid, one route line that draws itself between two cities, a small truck marker that
 * travels it, and two floating status chips. Pure SVG and CSS (no image files, no libraries). Decorative, so hidden from screen readers.
 */
export default function HeroRoute() {
  const { t } = useI18n()
  const reduced = useReducedMotion()
  return (
    <div className="hero-art relative mx-auto h-[300px] w-full max-w-5xl overflow-hidden rounded-3xl border border-line bg-wash sm:h-[380px]" aria-hidden="true" data-reduced={reduced}>
      <svg viewBox="0 0 1000 340" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full">
        <defs>
          <pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r="1.2" fill="var(--color-ink)" fillOpacity="0.16" /></pattern>
          <radialGradient id="fade" cx="50%" cy="50%" r="65%"><stop offset="55%" stopColor="#fff" /><stop offset="100%" stopColor="#000" /></radialGradient>
          <mask id="dotmask"><rect width="1000" height="340" fill="url(#fade)" /></mask>
        </defs>
        <rect width="1000" height="340" fill="url(#dots)" mask="url(#dotmask)" />
        <path d={PATH} fill="none" stroke="var(--color-muted)" strokeOpacity="0.55" strokeWidth="2" strokeDasharray="2 9" strokeLinecap="round" />
        <path d={PATH} fill="none" stroke="var(--color-ink)" strokeWidth="2.4" strokeLinecap="round" pathLength={1} className="hero-draw" />
        {[[110, 238], [890, 96]].map(([x, y]) => (
          <g key={x}>
            <circle cx={x} cy={y} r="14" fill="var(--color-surface)" stroke="var(--color-line)" />
            <circle cx={x} cy={y} r="5" fill="var(--color-ink)" />
          </g>
        ))}
        {!reduced && (
          <g>
            <circle r="9" fill="var(--color-ink)" />
            <circle r="3.2" fill="var(--color-surface)" />
            <animateMotion dur="7s" begin="2.6s" repeatCount="indefinite" path={PATH} keyPoints="0;1" keyTimes="0;1" calcMode="linear" />
          </g>
        )}
        <text x="110" y="276" textAnchor="middle" className="fill-[var(--color-muted)]" fontSize="13" fontWeight="500">Sambhajinagar</text>
        <text x="890" y="132" textAnchor="middle" className="fill-[var(--color-muted)]" fontSize="13" fontWeight="500">Pune</text>
      </svg>

      <div className="hero-float absolute left-4 top-5 flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2 text-sm font-medium sm:left-10 sm:top-8">
        <span className="h-2 w-2 rounded-full bg-accent" /> {t('land.chipBooked')}
      </div>
      <div className="hero-float hero-float-b absolute bottom-5 right-4 flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2 text-sm font-medium sm:bottom-8 sm:right-10">
        <span className="h-2 w-2 rounded-full bg-ok" /> {t('land.chipVerified')}
      </div>
    </div>
  )
}
