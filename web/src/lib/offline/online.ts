import { useSyncExternalStore } from 'react'

const subscribe = (cb: () => void) => {
  window.addEventListener('online', cb)
  window.addEventListener('offline', cb)
  return () => { window.removeEventListener('online', cb); window.removeEventListener('offline', cb) }
}

/** The browser's own idea of "is there a network". Not perfect (a captive portal says yes), so saved data and the outbox
 *  never depend on it: it only drives the "no network" label. */
export const useOnline = (): boolean => useSyncExternalStore(subscribe, () => navigator.onLine, () => true)

/** Whether the last try to talk to the server worked. A phone can have internet while the server is unreachable (the office computer is
 *  off, the tunnel is down): that is a different message from "no network". Starts as "yes" until a try fails. */
let serverUp = true
const listeners = new Set<() => void>()
export function markServer(up: boolean) {
  if (up === serverUp) return
  serverUp = up
  listeners.forEach((l) => l())
}
export const useServerUp = (): boolean => useSyncExternalStore((cb) => { listeners.add(cb); return () => { listeners.delete(cb) } }, () => serverUp, () => true)
