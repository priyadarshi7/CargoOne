import { CircleCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, tokenStore, type User } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'

/** Change your own password. Other signed-in devices are signed out; this one stays signed in. */
export default function Account() {
  const { user, adopt } = useAuth()
  const { t } = useI18n()
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
    if (next !== again) return setError(t('acct.mismatch'))
    setBusy(true)
    try {
      const res = await api<{ access_token: string }>('/auth/change-secret', { method: 'POST', body: JSON.stringify({ current, new: next }) })
      tokenStore.set(res.access_token)
      adopt(res.access_token, await api<User>('/auth/me')) // the screen now knows the temporary password is gone
      setCurrent(''); setNext(''); setAgain('')
      setDone(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('acct.offline'))
    } finally {
      setBusy(false)
    }
  }

  const input = 'w-full rounded-lg border border-line px-3 py-2.5 outline-none focus:border-accent'
  return (
    <div className="max-w-md space-y-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">{t('acct.title')}</h1>
        <p className="text-sm text-muted">{user?.name} · {user?.role}</p>
      </div>
      <p className="text-sm"><Link to="/progress" className="text-accent underline underline-offset-2">{t('nav.progress')}</Link></p>
      <form onSubmit={submit} className="space-y-5">
        <h2 className="font-semibold">{t('acct.change')}</h2>
        <label className="block space-y-1.5 text-sm"><span className="text-muted">{t('acct.current')}</span>
          <input className={input} type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required /></label>
        <label className="block space-y-1.5 text-sm"><span className="text-muted">{t('acct.new')}</span>
          <input className={input} type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} required /></label>
        <p className="-mt-3 text-xs text-muted">{t('acct.hint')}</p>
        <label className="block space-y-1.5 text-sm"><span className="text-muted">{t('acct.again')}</span>
          <input className={input} type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} required /></label>
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
        {done && <p role="status" className="flex items-center gap-2 text-sm text-ok"><CircleCheck size={16} aria-hidden /> {t('acct.done')}</p>}
        <button disabled={busy} className="rounded-lg bg-ink px-5 py-2.5 font-medium text-surface disabled:opacity-60">{busy ? t('acct.saving') : t('acct.change')}</button>
      </form>
    </div>
  )
}
