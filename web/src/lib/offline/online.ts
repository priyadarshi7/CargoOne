import { useSyncExternalStore } from 'react'

const subscribe = (cb: () => void) => {
  window.addEventListener('online', cb)
  window.addEventListener('offline', cb)
  return () => { window.removeEventListener('online', cb); window.removeEventListener('offline', cb) }
}

/** The browser's own idea of "is there a network". Not perfect (a captive portal says yes), so saved data and the outbox
 *  never depend on it: it only drives the "no network" label. */
export const useOnline = (): boolean => useSyncExternalStore(subscribe, () => navigator.onLine, () => true)
