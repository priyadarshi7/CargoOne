import { Truck } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { homeFor, useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'

export default function Login() {
  const { user, login } = useAuth()
  const { t } = useI18n()
  const nav = useNavigate()
  const [identifier, setIdentifier] = useState('')
  const [secret, setSecret] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={homeFor(user.role)} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const u = await login(identifier, secret)
      nav(homeFor(u.role), { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? (err.status === 401 ? t('login.wrong') : err.status === 429 ? err.message : t('login.offline')) : t('login.offline'))
    } finally {
      setBusy(false)
    }
  }

  const input = 'w-full rounded-lg border border-line px-3 py-2.5 text-base outline-none focus:border-accent'
  return (
    <div className="grid min-h-full place-items-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-5">
        <Link to="/" className="flex items-center gap-2 text-xl font-semibold">
          <Truck className="text-accent" aria-hidden /> CargoOne
        </Link>
        <label className="block space-y-1.5 text-sm">
          <span className="text-muted">{t('login.identifier')}</span>
          <input className={input} value={identifier} onChange={(e) => setIdentifier(e.target.value)}
            autoComplete="username" required autoFocus />
        </label>
        <label className="block space-y-1.5 text-sm">
          <span className="text-muted">{t('login.secret')}</span>
          <input className={input} type="password" value={secret} onChange={(e) => setSecret(e.target.value)}
            autoComplete="current-password" required />
        </label>
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
        <button disabled={busy}
          className="w-full rounded-lg bg-accent py-3 font-medium text-on-solid disabled:opacity-60">
          {busy ? t('login.busy') : t('login.submit')}
        </button>
        <p className="text-center text-sm text-muted">
          <Link to="/progress" className="underline underline-offset-2">{t('login.progress')}</Link>
        </p>
        <p className="text-center text-sm">
          <Link to="/request" className="font-medium text-accent underline underline-offset-2">{t('login.request')}</Link>
        </p>
      </form>
    </div>
  )
}
