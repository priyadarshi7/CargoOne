import { ArrowRight, FileCheck2, Languages, Link2, MapPinned, Send, ShieldCheck, Truck, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import { LANGUAGES, useI18n, type Lang } from '../lib/i18n'

const STEPS: { icon: LucideIcon; key: 's1' | 's2' | 's3' }[] = [
  { icon: Send, key: 's1' }, { icon: ShieldCheck, key: 's2' }, { icon: MapPinned, key: 's3' },
]
const BENEFITS: { icon: LucideIcon; key: 'w1' | 'w2' | 'w3' }[] = [
  { icon: Link2, key: 'w1' }, { icon: FileCheck2, key: 'w2' }, { icon: Languages, key: 'w3' },
]
const primary = 'inline-flex items-center justify-center gap-2 rounded-lg bg-accent px-6 py-3 font-medium text-on-solid'

/** The public front door at "/": what CargoOne is, how a company asks for a truck, and where staff and drivers sign in. */
export default function Landing() {
  const { t, lang, setLang } = useI18n()
  return (
    <div className="min-h-full">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-6">
          <span className="flex items-center gap-2 text-lg font-semibold"><Truck className="text-accent" aria-hidden /> CargoOne</span>
          <div className="ml-auto flex flex-wrap items-center gap-3 text-sm">
            <select aria-label="Language" value={lang} onChange={(e) => setLang(e.target.value as Lang)} className="rounded-lg border border-line bg-surface px-2 py-1.5 text-sm">
              {LANGUAGES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
            </select>
            <Link to="/login" className="whitespace-nowrap text-muted underline-offset-2 hover:text-ink hover:underline">{t('land.signIn')}</Link>
            <Link to="/request" className="hidden whitespace-nowrap rounded-lg bg-accent px-4 py-2 font-medium text-on-solid sm:inline-block">{t('land.requestShort')}</Link>
          </div>
        </div>
      </header>

      <main>
        <section className="bg-accent-soft">
          <div className="mx-auto max-w-5xl px-4 py-14 sm:px-6 sm:py-20">
            <h1 className="max-w-3xl text-3xl font-semibold leading-tight sm:text-5xl">{t('land.h1')}</h1>
            <p className="mt-5 max-w-2xl text-lg text-muted">{t('land.sub')}</p>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Link to="/request" className={primary}>{t('land.request')} <ArrowRight size={18} aria-hidden /></Link>
              <Link to="/login" className="text-sm font-medium text-accent underline underline-offset-2">{t('land.cta2')}</Link>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-5xl px-4 py-14 sm:px-6" aria-labelledby="how">
          <h2 id="how" className="text-2xl font-semibold">{t('land.how')}</h2>
          <ol className="mt-6 grid gap-4 md:grid-cols-3">
            {STEPS.map(({ icon: Icon, key }, i) => (
              <li key={key} className="rounded-xl border border-line p-5">
                <div className="flex items-center gap-3">
                  <span className="grid h-10 w-10 place-items-center rounded-full bg-accent-soft text-accent"><Icon size={20} aria-hidden /></span>
                  <span className="text-sm text-muted">{i + 1}</span>
                </div>
                <h3 className="mt-4 font-semibold">{t(`land.${key}.t`)}</h3>
                <p className="mt-1 text-sm text-muted">{t(`land.${key}.b`)}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="border-y border-line bg-wash" aria-labelledby="why">
          <div className="mx-auto max-w-5xl px-4 py-14 sm:px-6">
            <h2 id="why" className="text-2xl font-semibold">{t('land.why')}</h2>
            <ul className="mt-6 grid gap-4 md:grid-cols-3">
              {BENEFITS.map(({ icon: Icon, key }) => (
                <li key={key} className="rounded-xl bg-surface p-5">
                  <Icon size={22} className="text-accent" aria-hidden />
                  <h3 className="mt-3 font-semibold">{t(`land.${key}.t`)}</h3>
                  <p className="mt-1 text-sm text-muted">{t(`land.${key}.b`)}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="mx-auto max-w-5xl px-4 py-14 sm:px-6">
          <div className="grid items-center gap-8 md:grid-cols-2">
            <div>
              <h2 className="text-2xl font-semibold">{t('land.finalTitle')}</h2>
              <p className="mt-2 text-muted">{t('land.finalBody')}</p>
              <Link to="/request" className={`${primary} mt-5`}>{t('land.request')} <ArrowRight size={18} aria-hidden /></Link>
            </div>
            <div className="rounded-xl border border-line p-5">
              <h3 className="font-semibold">{t('land.have')}</h3>
              <p className="mt-1 text-sm text-muted">{t('land.haveBody')}</p>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-2 px-4 py-5 text-sm text-muted sm:px-6">
          <span>{t('land.privacy')}</span>
          <Link to="/login" className="underline underline-offset-2">{t('land.signIn')}</Link>
        </div>
      </footer>
    </div>
  )
}
