import { ArrowRight, Check, FileCheck2, MessageCircle, Route, Truck, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import HeroScene from '../components/HeroScene'
import { ThemeToggle } from '../components/ThemeToggle'
import { LANGUAGES, useI18n, type Lang } from '../lib/i18n'

const STEPS = ['s1', 's2', 's3'] as const
const FACTS: { icon: LucideIcon; key: 'f1' | 'f2' | 'f3' | 'f4' }[] = [
  { icon: Truck, key: 'f1' }, { icon: FileCheck2, key: 'f2' }, { icon: Route, key: 'f3' }, { icon: MessageCircle, key: 'f4' },
]
const BENEFITS = ['w1', 'w2', 'w3', 'w4'] as const
const PREVIEW = ['pv.s1', 'pv.s2', 'pv.s3'] as const
const solid = 'inline-flex items-center justify-center gap-2 rounded-xl bg-ink px-7 py-3.5 text-base font-medium text-surface hover:opacity-90'
const outline = 'inline-flex items-center justify-center gap-2 rounded-xl border border-ink/15 bg-surface/70 px-7 py-3.5 text-base font-medium hover:bg-surface'
const wrap = 'mx-auto w-full max-w-6xl px-5 sm:px-8'

/** The public front door at "/": what CargoOne does, how a company asks for a truck, and where staff and drivers sign in. */
export default function Landing() {
  const { t, lang, setLang } = useI18n()
  return (
    <div className="min-h-full">
      <div className="sky">
      <header>
        <div className={`${wrap} flex h-16 items-center gap-3`}>
          <span className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-ink text-surface"><Truck size={16} aria-hidden /></span> CargoOne
          </span>
          <div className="ml-auto flex items-center gap-2 text-sm">
            <select aria-label="Language" value={lang} onChange={(e) => setLang(e.target.value as Lang)} className="h-9 rounded-lg border border-line bg-surface px-2 text-sm">
              {LANGUAGES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
            </select>
            <ThemeToggle />
            <Link to="/login" className="hidden whitespace-nowrap rounded-lg px-3 py-2 text-muted hover:text-ink sm:inline-block">{t('land.signIn')}</Link>
            <Link to="/request" className="whitespace-nowrap rounded-lg bg-ink px-4 py-2 font-medium text-surface hover:opacity-90">{t('land.requestShort')}</Link>
          </div>
        </div>
      </header>

        <section className={`${wrap} flex flex-col items-center gap-6 pb-4 pt-12 text-center sm:pt-20`}>
          <span className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-surface/70 px-3 py-1 text-xs font-medium text-ink"><span className="h-1.5 w-1.5 rounded-full bg-ok" /> {t('land.badge')}</span>
          <h1 className="max-w-4xl text-balance text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl">{t('land.h1')}</h1>
          <p className="max-w-xl text-lg leading-relaxed text-ink/75">{t('land.sub')}</p>
          <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
            <Link to="/request" className={solid}>{t('land.request')} <ArrowRight size={18} aria-hidden /></Link>
            <Link to="/login" className={outline}>{t('land.cta2')}</Link>
          </div>
          <p className="text-sm text-ink/60">{t('land.note')}</p>
        </section>
        <HeroScene />
      </div>

      <main>
        <section className={`${wrap} py-10`} aria-label="CargoOne">
          <ul className="grid grid-cols-2 gap-x-6 gap-y-5 md:grid-cols-4">
            {FACTS.map(({ icon: Icon, key }) => (
              <li key={key} className="flex items-center gap-3 text-sm font-medium">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-line text-ink"><Icon size={18} aria-hidden /></span>
                {t(`land.${key}`)}
              </li>
            ))}
          </ul>
        </section>

        <section className={`${wrap} pb-24 pt-6`} aria-label={t('land.pv.sample')}>
          <div className="mx-auto max-w-4xl overflow-hidden rounded-2xl border border-line">
            <div className="flex flex-wrap items-center gap-3 border-b border-line bg-wash px-5 py-3.5">
              <span className="font-mono text-xs">REQ-1001</span>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-medium text-accent"><span className="h-1.5 w-1.5 rounded-full bg-accent" /> {t('req.status.booked')}</span>
              <span className="ml-auto text-xs text-muted">{t('land.pv.sample')}</span>
            </div>
            <div className="grid md:grid-cols-2">
              <div className="space-y-6 p-7 md:border-r md:border-line">
                <div>
                  <div className="text-xs font-medium uppercase tracking-wider text-muted">{t('land.pv.route')}</div>
                  <div className="mt-1.5 text-xl font-semibold tracking-tight">Chhatrapati Sambhajinagar <span className="font-normal text-muted">{t('land.pv.to')}</span> Pune</div>
                  <div className="mt-1 text-sm text-muted">{t('land.pv.detail')}</div>
                </div>
                <ol className="space-y-0">
                  {PREVIEW.map((k) => (
                    <li key={k} className="flex gap-3.5">
                      <span className="flex flex-col items-center"><span className="grid h-[22px] w-[22px] place-items-center rounded-full bg-ink text-surface"><Check size={13} aria-hidden /></span><span className="min-h-5 w-px flex-1 bg-line" /></span>
                      <span className="pb-4 text-sm font-medium">{t(`land.${k}`)}</span>
                    </li>
                  ))}
                  <li className="flex gap-3.5">
                    <span className="h-[22px] w-[22px] shrink-0 rounded-full border border-line" />
                    <span><span className="block text-sm font-medium text-muted">{t('land.pv.s4')}</span><span className="text-xs text-muted">{t('land.pv.s4d')}</span></span>
                  </li>
                </ol>
              </div>
              <div className="flex flex-col gap-3.5 bg-wash p-7">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium uppercase tracking-wider text-muted">{t('land.pv.receipt')}</span>
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-ok-soft px-2.5 py-0.5 text-xs font-medium text-ok"><span className="h-1.5 w-1.5 rounded-full bg-ok" /> {t('land.pv.verified')}</span>
                </div>
                <div className="flex min-h-52 flex-1 flex-col gap-2.5 rounded-xl border border-line bg-surface p-5" aria-hidden="true">
                  <span className="h-2 w-2/5 rounded bg-line" /><span className="h-2 w-3/4 rounded bg-wash" /><span className="h-2 w-1/2 rounded bg-wash" />
                  <span className="mt-auto flex items-end justify-between"><span className="font-mono text-xs text-muted">LR/MH20/26-27/000123</span><span className="border-b border-line text-xl italic text-muted">A. Mehta</span></span>
                </div>
                <span className="text-xs text-muted">{t('land.pv.illus')}</span>
              </div>
            </div>
          </div>
        </section>

        <section className={`${wrap} pb-24`} aria-labelledby="how">
          <span className="text-xs font-medium uppercase tracking-wider text-muted">{t('land.how')}</span>
          <h2 id="how" className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">{t('land.how.title')}</h2>
          <ol className="mt-8 grid gap-4 md:grid-cols-3">
            {STEPS.map((k, i) => (
              <li key={k} className="rounded-2xl border border-line p-7">
                <span className="font-mono text-sm text-muted">0{i + 1}</span>
                <h3 className="mt-6 text-xl font-semibold tracking-tight">{t(`land.${k}.t`)}</h3>
                <p className="mt-2 text-muted">{t(`land.${k}.b`)}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className={`${wrap} pb-24`} aria-labelledby="why">
          <span className="text-xs font-medium uppercase tracking-wider text-muted">{t('land.why')}</span>
          <h2 id="why" className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">{t('land.why.title')}</h2>
          <ul className="mt-8 grid gap-4 md:grid-cols-2">
            {BENEFITS.map((k) => (
              <li key={k} className="rounded-2xl bg-wash p-7">
                <h3 className="text-xl font-semibold tracking-tight">{t(`land.${k}.t`)}</h3>
                <p className="mt-2 max-w-md text-muted">{t(`land.${k}.b`)}</p>
                {k === 'w3' && <div className="mt-4 flex gap-2">{LANGUAGES.map(([v, label]) => <span key={v} className="rounded-full border border-line bg-surface px-3 py-1 text-sm">{label}</span>)}</div>}
              </li>
            ))}
          </ul>
        </section>

        <section className={`${wrap} pb-24`}>
          <div className="flex flex-col items-center gap-5 rounded-3xl bg-ink px-6 py-16 text-center text-surface">
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t('land.finalTitle')}</h2>
            <p className="max-w-md opacity-75">{t('land.finalBody')}</p>
            <Link to="/request" className="inline-flex items-center gap-2 rounded-xl bg-surface px-7 py-3.5 text-base font-medium text-ink hover:opacity-90">{t('land.request')} <ArrowRight size={18} aria-hidden /></Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className={`${wrap} flex flex-wrap items-center justify-between gap-2 py-6 text-sm text-muted`}>
          <span>{t('land.privacy')}</span>
          <Link to="/login" className="underline underline-offset-2">{t('land.signIn')}</Link>
        </div>
      </footer>
    </div>
  )
}
