/** The Google map, loaded only when a page needs it (about 200 KB the app never pays otherwise). The key is the browser key from the server,
 *  which Google expects to be public and restricts by site; a refused key (wrong site, API not enabled) is reported, not hidden. */
export interface LatLng { lat: number; lng: number }
export interface GMap {
  getCenter(): { lat(): number; lng(): number } | undefined
  setCenter(p: LatLng): void
  panTo(p: LatLng): void
  setZoom(z: number): void
  addListener(event: string, fn: () => void): { remove(): void }
}
export interface GMapsApi { importLibrary(name: string): Promise<{ Map: new (el: HTMLElement, opts: Record<string, unknown>) => GMap }> }

declare global { interface Window { google?: { maps?: GMapsApi }; gm_authFailure?: () => void } }

let loading: Promise<GMapsApi> | null = null

export function loadGoogleMaps(key: string): Promise<GMapsApi> {
  if (window.google?.maps?.importLibrary) return Promise.resolve(window.google.maps)
  if (loading) return loading
  loading = new Promise<GMapsApi>((resolve, reject) => {
    window.gm_authFailure = () => { loading = null; reject(new Error('key refused')) } // Google calls this when the key does not allow this site or an API is off
    const s = document.createElement('script')
    s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&v=weekly&loading=async&language=en&region=IN`
    s.async = true
    s.onload = () => (window.google?.maps ? resolve(window.google.maps) : (loading = null, reject(new Error('map did not start'))))
    s.onerror = () => { loading = null; reject(new Error('map script failed')) }
    document.head.appendChild(s)
  })
  return loading
}
