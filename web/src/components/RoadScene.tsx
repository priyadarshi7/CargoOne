import type { ReactNode } from 'react'

/** The CargoOne truck, drawn in a 520 x 170 box (wheels end at y 168). The colours are passed in so it works on the light hero and on the dark closing block. */
export function TruckArt({ body = 'var(--truck-body)', line = 'var(--truck-line)', cab = 'var(--truck-cab)', glass = 'var(--scene-window)', label = 'var(--truck-line)', children }: {
  body?: string; line?: string; cab?: string; glass?: string; label?: string; children?: ReactNode
}) {
  return (
    <>
      <rect x="10" y="130" width="500" height="9" rx="3" fill={cab} />
      <rect x="10" y="22" width="334" height="108" rx="8" fill={body} stroke={line} strokeWidth="3" />
      <rect x="11.5" y="92" width="331" height="16" fill="var(--color-accent)" />
      <text x="34" y="72" fontSize="34" fontWeight="700" letterSpacing="-0.7" fill={label}>CargoOne</text>
      <path d="M352 130 V 58 Q 352 44 366 44 H 432 Q 444 44 452 56 L 484 98 Q 492 108 492 120 V 130 Z" fill={cab} />
      <path d="M372 58 H 430 L 460 100 H 372 Z" fill={glass} />
      <rect x="484" y="108" width="9" height="11" rx="2" fill="var(--scene-light)" />
      <rect x="358" y="14" width="7" height="34" rx="2" fill="var(--color-muted)" />
      {[62, 116, 388, 448].map((cx) => (
        <g key={cx} transform={`translate(${cx} 146)`}>
          <circle r="22" fill={cab} stroke={line} strokeWidth="2" />
          <g className="scene-wheel"><circle r="9" fill="var(--scene-hub)" /><line x1="-8" y1="0" x2="8" y2="0" stroke={cab} strokeWidth="2.5" /></g>
        </g>
      ))}
      {children}
    </>
  )
}

/** The hero picture: soft hills, a road with moving lane marks, and the loaded CargoOne truck driving along it. Pure SVG and CSS, decorative.
 *  The truck, lane marks and wheels move only when the device allows motion; otherwise the truck is parked mid-road (index.css turns the animations off). */
export default function RoadScene() {
  return (
    <div className="pointer-events-none relative h-[140px] overflow-hidden sm:h-[170px]" aria-hidden="true">
      <svg viewBox="0 90 1440 160" preserveAspectRatio="xMidYMax slice" className="absolute inset-0 h-full w-full">
        <path d="M0 140 C 160 90, 300 90, 460 130 S 760 100, 940 130 S 1260 90, 1440 120 V 250 H 0 Z" fill="var(--scene-hill-far)" />
        <path d="M0 184 C 200 144, 380 154, 560 178 S 900 154, 1100 174 S 1360 154, 1440 168 V 250 H 0 Z" fill="var(--scene-hill-near)" />
        <rect x="0" y="206" width="1440" height="44" fill="var(--scene-road)" />
        <line x1="0" y1="228" x2="1440" y2="228" stroke="var(--scene-lane)" strokeWidth="3" strokeDasharray="38 30" className="scene-lane" />
        <g className="scene-truck"><g transform="translate(0 92) scale(0.82)"><TruckArt /></g></g>
      </svg>
    </div>
  )
}
