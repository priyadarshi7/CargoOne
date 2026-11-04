export interface Position {
  lat: number
  lng: number
}

/** Best-effort GPS fix. Never blocks the driver: resolves null on denial, timeout or no GPS. */
export function getPosition(timeoutMs = 4000): Promise<Position | null> {
  return new Promise((resolve) => {
    if (!('geolocation' in navigator)) return resolve(null)
    const timer = setTimeout(() => resolve(null), timeoutMs + 500)
    navigator.geolocation.getCurrentPosition(
      (p) => {
        clearTimeout(timer)
        resolve({ lat: p.coords.latitude, lng: p.coords.longitude })
      },
      () => {
        clearTimeout(timer)
        resolve(null)
      },
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 60_000 },
    )
  })
}
