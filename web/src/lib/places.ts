import { api } from './api'

export interface Place { id?: string | null; label: string; name: string; detail: string; lat: number | null; lng: number | null }
export type Pos = { lat: number; lng: number } | null
export interface PlacesConfig { provider: 'google' | 'photon'; maps_key: string | null }

/** One per search-then-pick. The provider bills a search that ends in a pick as a single session, so a new one starts after every pick. */
export const newSession = (): string => {
  try { return crypto.randomUUID().replace(/-/g, '') } catch { return `s${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}` }
}

export const searchPlaces = (q: string, session: string) => api<Place[]>(`/places/search?q=${encodeURIComponent(q)}&session=${session}`)
export const placeDetails = (id: string, session: string) => api<Place>(`/places/details?id=${encodeURIComponent(id)}&session=${session}`)
export const reversePlace = (lat: number, lng: number) => api<Place>(`/places/reverse?lat=${lat}&lng=${lng}`)

let config: Promise<PlacesConfig> | null = null
/** Which provider is in use, and the browser key for the map. Asked once; a failed ask is tried again next time. */
export function placesConfig(): Promise<PlacesConfig> {
  if (!config) config = api<PlacesConfig>('/places/config').catch(() => { config = null; return { provider: 'photon' as const, maps_key: null } })
  return config
}
