import { useEffect, useState } from 'react'
import { flush, pendingCount } from './queue'
import { uploadPod } from './upload'

/** Keeps the offline queue draining: on start, when the network returns, and every 30 s.
 *  Returns how many photos are still waiting on this device. */
export function useSyncedQueue(): number {
  const [pending, setPending] = useState(0)

  useEffect(() => {
    let alive = true
    const sync = async () => {
      await flush(uploadPod).catch(() => undefined)
      const n = await pendingCount()
      if (alive) setPending(n)
    }
    void sync()
    window.addEventListener('online', sync)
    const timer = setInterval(sync, 30_000)
    return () => {
      alive = false
      window.removeEventListener('online', sync)
      clearInterval(timer)
    }
  }, [])

  return pending
}
