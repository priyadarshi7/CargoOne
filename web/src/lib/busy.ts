import { useCallback, useState } from 'react'

/** For buttons that start a request: `run('key', work)` marks that key busy until the work ends, and ignores a second click meanwhile.
 *  `busy === 'key'` is what the button reads to disable itself and show a spinner and "Working…". */
export function useBusy() {
  const [busy, setBusy] = useState<string | null>(null)
  const run = useCallback(async (key: string, work: () => Promise<unknown>) => {
    if (busy) return
    setBusy(key)
    try { await work() } finally { setBusy(null) }
  }, [busy])
  return { busy, run }
}
