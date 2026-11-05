/**
 * The landing hero picture: a pale sky, slow clouds, soft hills and a loaded container truck driving along a road.
 * Pure SVG and CSS (no image files, no libraries), decorative so hidden from screen readers. The truck, clouds and wheels move
 * only when the device allows motion; otherwise the truck is parked mid-road (the rule in index.css turns the animations off).
 */
export default function HeroScene() {
  return (
    <div className="hero-scene pointer-events-none relative mx-auto h-[170px] w-full overflow-hidden sm:h-[250px]" aria-hidden="true">
      <svg viewBox="0 0 1440 250" preserveAspectRatio="xMidYMax slice" className="absolute inset-0 h-full w-full">
        <g className="scene-cloud scene-cloud-a" fill="var(--scene-cloud)">
          <rect x="180" y="52" width="150" height="26" rx="13" /><rect x="210" y="36" width="80" height="30" rx="15" />
        </g>
        <g className="scene-cloud scene-cloud-b" fill="var(--scene-cloud)">
          <rect x="860" y="30" width="190" height="30" rx="15" /><rect x="900" y="12" width="100" height="32" rx="16" />
        </g>
        <g className="scene-cloud scene-cloud-c" fill="var(--scene-cloud)" opacity="0.8">
          <rect x="1180" y="86" width="120" height="22" rx="11" /><rect x="1204" y="72" width="64" height="24" rx="12" />
        </g>

        <path d="M0 196 C 140 150, 260 150, 400 182 S 640 150, 800 176 S 1100 140, 1260 172 S 1400 168, 1440 160 V 214 H 0 Z" fill="var(--scene-hill-far)" />
        <path d="M0 208 C 180 178, 330 190, 520 200 S 860 176, 1040 196 S 1340 184, 1440 196 V 214 H 0 Z" fill="var(--scene-hill-near)" />

        <rect x="0" y="212" width="1440" height="38" fill="var(--scene-road)" />
        <line x1="0" y1="232" x2="1440" y2="232" stroke="var(--scene-lane)" strokeWidth="2" strokeDasharray="26 22" className="scene-lane" />

        <g transform="translate(0 226)"><g className="scene-truck">
          <g>
            <rect x="0" y="-122" width="214" height="88" rx="7" fill="var(--truck-body)" stroke="var(--truck-line)" strokeWidth="1.6" />
            {[28, 56, 84, 112, 140, 168, 196].map((x) => <line key={x} x1={x} y1="-118" x2={x} y2="-38" stroke="var(--truck-line)" strokeOpacity="0.35" />)}
            <text x="107" y="-70" textAnchor="middle" fontSize="19" fontWeight="600" letterSpacing="-0.4" fill="var(--truck-line)">CargoOne</text>
            <rect x="0" y="-34" width="304" height="8" rx="2" fill="var(--truck-cab)" />
            <path d="M222 -26 V-90 H252 L284 -58 H304 V-26 Z" fill="var(--truck-cab)" />
            <path d="M231 -82 H249 L272 -60 H231 Z" fill="var(--scene-window)" />
            <rect x="296" y="-48" width="8" height="8" rx="2" fill="var(--scene-light)" />
          </g>
          {[44, 76, 262].map((cx) => (
            <g key={cx} transform={`translate(${cx} -16)`}>
              <circle r="16" fill="var(--truck-cab)" />
              <g className="scene-wheel"><circle r="7" fill="var(--scene-hub)" /><line x1="-6" y1="0" x2="6" y2="0" stroke="var(--truck-cab)" strokeWidth="2" /></g>
            </g>
          ))}
        </g></g>
      </svg>
    </div>
  )
}
