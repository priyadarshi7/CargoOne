import { Eye, EyeOff, LayoutDashboard, Receipt, Smartphone, Truck, type LucideIcon } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { homeFor, useAuth } from '../lib/auth'
import { LANGUAGES, useI18n, type Lang } from '../lib/i18n'

const ROLES: { icon: LucideIcon; k: 'driver' | 'ops' | 'billing' | 'md' }[] = [
  { icon: Smartphone, k: 'driver' }, { icon: Truck, k: 'ops' }, { icon: Receipt, k: 'billing' }, { icon: LayoutDashboard, k: 'md' },
]
const input = 'h-11 w-full rounded-lg border border-line bg-surface px-3.5 text-base outline-none focus:border-ink'

export default function Login() {
  const { user, login } = useAuth()
  const { t, lang, setLang } = useI18n()
  const nav = useNavigate()
  const [identifier, setIdentifier] = useState('')
  const [secret, setSecret] = useState('')
  const [show, setShow] = useState(false)
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

  return (
    <div className="flex min-h-full">
      <main className="flex min-w-0 flex-1 flex-col px-6 py-6 sm:px-10">
        <div className="flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5 text-lg font-semibold tracking-tight">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-ink text-surface"><Truck size={16} aria-hidden /></span> CargoOne
          </Link>
          <select aria-label="Language" value={lang} onChange={(e) => setLang(e.target.value as Lang)} className="h-9 rounded-lg border border-line bg-surface px-2 text-sm text-muted">
            {LANGUAGES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
        </div>

        <form onSubmit={submit} className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-5 py-12">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t('login.title')}</h1>
            <p className="mt-1.5 text-muted">{t('login.sub')}</p>
          </div>
          <label className="block space-y-1.5 text-sm">
            <span className="font-medium">{t('login.identifier')}</span>
            <input className={input} value={identifier} onChange={(e) => setIdentifier(e.target.value)} autoComplete="username" required autoFocus />
          </label>
          <div className="space-y-1.5 text-sm">
            <label htmlFor="secret" className="font-medium">{t('login.secret')}</label>
            <div className="relative">
              <input id="secret" className={`${input} pr-12`} type={show ? 'text' : 'password'} value={secret} onChange={(e) => setSecret(e.target.value)} autoComplete="current-password" required />
              <button type="button" onClick={() => setShow(!show)} aria-label={show ? t('login.hide') : t('login.show')} aria-pressed={show} className="absolute right-1 top-1 grid h-9 w-9 place-items-center rounded-md text-muted hover:text-ink">
                {show ? <EyeOff size={18} aria-hidden /> : <Eye size={18} aria-hidden />}
              </button>
            </div>
            <p className="text-xs text-muted">{t('login.forgot')}</p>
          </div>
          {error && <p role="alert" className="rounded-lg bg-bad-soft px-3 py-2 text-sm text-bad">{error}</p>}
          <button disabled={busy} className="h-12 w-full rounded-xl bg-ink text-base font-medium text-surface hover:opacity-90 disabled:opacity-60">
            {busy ? t('login.busy') : t('login.submit')}
          </button>
          <div className="space-y-2.5 border-t border-line pt-5">
            <p className="text-sm text-muted">{t('login.needTruck')}</p>
            <Link to="/request" className="flex h-11 w-full items-center justify-center rounded-lg border border-line text-sm font-medium hover:bg-wash">{t('land.request')}</Link>
            <p className="pt-1 text-center text-xs"><Link to="/progress" className="text-muted underline underline-offset-2">{t('login.progress')}</Link></p>
          </div>
        </form>
        <p className="mx-auto w-full max-w-sm text-xs text-muted">{t('login.shared')}</p>
      </main>

      <aside className="hidden flex-1 flex-col justify-center gap-7 border-l border-line bg-wash px-14 lg:flex">
        <span className="text-xs font-medium uppercase tracking-wider text-muted">{t('login.eyebrow')}</span>
        <h2 className="max-w-md text-3xl font-semibold leading-tight tracking-tight">{t('login.panelH')}</h2>
        <ul className="max-w-md divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
          {ROLES.map(({ icon: Icon, k }) => (
            <li key={k} className="flex items-center gap-4 px-5 py-4">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-line bg-wash"><Icon size={18} aria-hidden /></span>
              <span><span className="block font-medium">{t(`login.r.${k}`)}</span><span className="block text-sm text-muted">{t(`login.r.${k}B`)}</span></span>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  )
}
