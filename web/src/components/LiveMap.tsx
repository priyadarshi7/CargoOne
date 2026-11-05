import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef } from 'react'

export interface MapPoint { id: string; lat: number; lng: number; label: string; tone: 'ok' | 'warn' | 'bad' | 'muted' }

/** OpenStreetMap map with simple round pins. Tiles are the free public OSM server (fine for a pilot; production should
 *  use a hosted tile provider with a key). In dark mode the tiles are inverted by CSS (see index.css). */
export function LiveMap({ points, path, selectedId, onSelect, label }: {
  points: MapPoint[]; path?: [number, number][]; selectedId?: string | null; onSelect?: (id: string) => void; label: string
}) {
  const box = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layer = useRef<L.LayerGroup | null>(null)
  const fitted = useRef(false)

  useEffect(() => {
    if (!box.current || map.current) return
    const m = L.map(box.current, { zoomControl: true, attributionControl: true }).setView([19.8762, 75.3433], 7)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '© OpenStreetMap contributors' }).addTo(m)
    layer.current = L.layerGroup().addTo(m)
    map.current = m
    return () => { m.remove(); map.current = null }
  }, [])

  useEffect(() => {
    const m = map.current, g = layer.current
    if (!m || !g) return
    g.clearLayers()
    if (path && path.length > 1) L.polyline(path, { color: '#2a78d6', weight: 3, opacity: 0.8 }).addTo(g)
    for (const p of points) {
      const icon = L.divIcon({ className: '', html: `<span class="map-pin map-pin-${p.tone}${p.id === selectedId ? ' map-pin-selected' : ''}"></span>`, iconSize: [22, 22], iconAnchor: [11, 11] })
      const mk = L.marker([p.lat, p.lng], { icon, title: p.label, alt: p.label, keyboard: true }).addTo(g)
      mk.on('click', () => onSelect?.(p.id))
    }
    if (!fitted.current && points.length) {
      fitted.current = true
      m.fitBounds(L.latLngBounds(points.map((p) => [p.lat, p.lng] as [number, number])), { padding: [48, 48], maxZoom: 12 })
    }
  }, [points, path, selectedId, onSelect])

  useEffect(() => {
    const p = points.find((x) => x.id === selectedId)
    if (p && map.current) map.current.flyTo([p.lat, p.lng], Math.max(map.current.getZoom(), 11), { duration: 0.6 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId])

  return <div ref={box} role="application" aria-label={label} className="h-[26rem] w-full overflow-hidden rounded-xl border border-line lg:h-full lg:min-h-[28rem]" />
}
