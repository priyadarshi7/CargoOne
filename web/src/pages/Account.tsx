import { CircleCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { api, ApiError, tokenStore } from '../lib/api'
import { useAuth } from '../lib/auth'

/** Change your own password. Other signed-in devices are signed out; this one stays signed in. */
export default function Account() {
  const { user } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setDone(false)
    if (next !== again) return setError('The two new passwords are not the same.')
    setBusy(true)
    try {
      const res = await api<{ access_token: string }>('/auth/change-secret', { method: 'POST', body: JSON.stringify({ current, new: next }) })
      tokenStore.set(res.access_token)
      setCurrent(''); setNext(''); setAgain('')
      setDone(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not reach the server.')
    } finally {
      setBusy(false)
    }
  }

  const input = 'w-full rounded-lg border border-line px-3 py-2.5 outline-none focus:border-accent'
  return (
    <div className="max-w-md space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Account</h1>
        <p className="text-sm text-muted">{user?.name} · {user?.role}</p>
      </div>
      <form onSubmit={submit} className="space-y-5">
        <h2 className="font-semibold">Change password</h2>
        <label className="block space-y-1.5 text-sm"><span className="text-muted">Current password</span>
          <input className={input} type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required /></label>
        <label className="block space-y-1.5 text-sm"><span className="text-muted">New password</span>
          <input className={input} type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} required /></label>
        <p className="-mt-3 text-xs text-muted">At least 10 characters, with letters. Not your name or a common word.</p>
        <label className="block space-y-1.5 text-sm"><span className="text-muted">New password again</span>
          <input className={input} type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} required /></label>
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
        {done && <p role="status" className="flex items-center gap-2 text-sm text-ok"><CircleCheck size={16} aria-hidden /> Password changed. Your other devices were signed out.</p>}
        <button disabled={busy} className="rounded-lg bg-accent px-5 py-2.5 font-medium text-on-solid disabled:opacity-60">{busy ? 'Saving…' : 'Change password'}</button>
      </form>
    </div>
  )
}
