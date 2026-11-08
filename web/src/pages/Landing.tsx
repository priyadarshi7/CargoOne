import { ArrowRight, Check, FileCheck2, MessageCircle, Route, Truck, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import RoadScene, { TruckArt } from '../components/RoadScene'
import { ThemeToggle } from '../components/ThemeToggle'
import { LANGUAGES, useI18n, type Lang } from '../lib/i18n'

const FACTS: { icon: LucideIcon; key: 'f1' | 'f2' | 'f3' | 'f4' }[] = [
  { icon: Truck, key: 'f1' }, { icon: FileCheck2, key: 'f2' }, { icon: Route, key: 'f3' }, { icon: MessageCircle, key: 'f4' },
]
const BENEFITS = ['w1', 'w2', 'w3', 'w4'] as const
const PREVIEW = ['pv.s1', 'pv.s2', 'pv.s3'] as const
const FORM_CHIPS = ['c.pickup', 'c.delivery', 'c.material', 'c.weight', 'c.date'] as const
const solid = 'inline-flex items-center justify-center gap-2.5 rounded-xl bg-accent px-7 py-4 text-base font-medium text-on-solid hover:opacity-90'
const outline = 'inline-flex items-center justify-center gap-2 rounded-xl border border-ink/30 px-7 py-4 text-base font-medium hover:border-ink hover:bg-surface'
const wrap = 'mx-auto w-full max-w-[1200px] px-5 sm:px-8'
const eyebrow = 'text-[13px] font-medium uppercase tracking-[0.1em] text-accent'
const h2 = 'mt-3 text-[clamp(2rem,4.4vw,3rem)] font-semibold leading-[1.08] tracking-[-0.03em]'
const chip = 'rounded-full border border-line bg-wash px-3 py-1 text-[13px]'
const card = 'flex min-w-0 flex-1 basis-[300px] flex-col gap-3.5 rounded-[20px] border border-line p-8 hover:border-ink'

/** The public front door at "/": what CargoOne does, how a company asks for a truck, and where everyone signs in. */
export default function Landing() {
  const { t, lang, setLang } = useI18n()
  return (
    <div className="min-h-full">
      <header className="border-b border-line">
        <div className={`${wrap} flex h-[72px] items-center gap-3 sm:gap-4`}>
          <a href="#top" aria-label="CargoOne" className="flex items-center gap-2.5 text-xl font-semibold tracking-tight">
            <span className="grid h-8 w-8 place-items-center rounded-[9px] bg-ink text-surface"><Truck size={18} aria-hidden /></span> <span className="max-[380px]:hidden">CargoOne</span>
          </a>
          <nav aria-label="CargoOne" className="ml-6 hidden gap-7 text-[15px] text-muted md:flex">
            <a href="#how" className="hover:text-ink">{t('land.how')}</a>
            <a href="#why" className="hover:text-ink">{t('land.why')}</a>
            <a href="#languages" className="hover:text-ink">{t('land.nav.lang')}</a>
          </nav>
          <div className="ml-auto flex items-center gap-2 text-sm">
            <select aria-label="Language" value={lang} onChange={(e) => setLang(e.target.value as Lang)} className="h-9 rounded-lg border border-line bg-surface px-2 text-sm">
              {LANGUAGES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
            </select>
            <span className="hidden sm:block"><ThemeToggle /></span>
            <Link to="/login" className="hidden whitespace-nowrap rounded-lg px-3 py-2 text-[15px] font-medium text-muted hover:text-ink sm:inline-block">{t('land.signIn')}</Link>
            <Link to="/request" className="whitespace-nowrap rounded-[10px] bg-ink px-4 py-2.5 text-[15px] font-medium text-surface hover:opacity-90">{t('land.requestShort')}</Link>
          </div>
        </div>
      </header>

      <section id="top" className="border-b border-line bg-wash">
        <div className={`${wrap} flex flex-wrap items-center gap-x-16 gap-y-12 pb-14 pt-10 sm:pt-20`}>
          <div className="flex min-w-0 flex-[1_1_480px] flex-col items-start gap-7">
            <span className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3.5 py-1.5 text-[13px] font-medium"><span className="h-[7px] w-[7px] rounded-full bg-ok" /> {t('land.badge')}</span>
            <h1 className="text-balance text-[clamp(2.6rem,6vw,4.5rem)] font-semibold leading-[1.02] tracking-[-0.035em]">{t('land.h1')}</h1>
            <p className="max-w-[520px] text-[19px] leading-relaxed text-ink/80">{t('land.sub')}</p>
            <div className="flex flex-wrap gap-3 pt-1">
              <Link to="/request" className={solid}>{t('land.request')} <ArrowRight size={18} aria-hidden /></Link>
              <Link to="/login" className={outline}>{t('land.cta2')}</Link>
            </div>
            <p className="text-sm text-muted">{t('land.note')}</p>
          </div>

          <div className="mx-auto min-w-0 max-w-[560px] flex-[1_1_440px]">
            <div className="overflow-hidden rounded-[20px] border border-line bg-surface shadow-[0_30px_70px_-30px_rgba(14,14,16,0.3)]">
              <div className="flex flex-wrap items-center gap-2.5 border-b border-line bg-wash px-5 py-3.5">
                <span className="font-mono text-[12.5px]">REQ-1001</span>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-medium text-accent"><span className="h-1.5 w-1.5 rounded-full bg-accent" /> {t('req.status.booked')}</span>
                <span className="ml-auto text-xs text-muted">{t('land.pv.sample')}</span>
              </div>
              <div className="px-6 pb-2 pt-6">
                <div className="text-xs font-medium uppercase tracking-[0.08em] text-muted">{t('land.pv.route')}</div>
                <div className="mt-2 text-[22px] font-semibold leading-tight tracking-tight">Chhatrapati Sambhajinagar <span className="font-normal text-muted">{t('land.pv.to')}</span> Pune</div>
                <div className="mt-1.5 text-sm text-muted">{t('land.pv.detail')}</div>
              </div>
              <ol className="px-6 pb-14 pt-5">
                {PREVIEW.map((k, i) => (
                  <li key={k} className="flex gap-3.5">
                    <span className="flex flex-col items-center"><span className="grid h-[22px] w-[22px] place-items-center rounded-full bg-ink text-surface"><Check size={13} strokeWidth={3} aria-hidden /></span><span className={`min-h-[18px] w-0.5 flex-1 ${i < 2 ? 'bg-ink' : 'bg-line'}`} /></span>
                    <span className="pb-4 text-[15px] font-medium">{t(`land.${k}`)}</span>
                  </li>
                ))}
                <li className="flex gap-3.5">
                  <span className="h-[22px] w-[22px] shrink-0 rounded-full border-2 border-line" />
                  <span><span className="block text-[15px] font-medium text-muted">{t('land.pv.s4')}</span><span className="text-[13px] text-muted">{t('land.pv.s4d')}</span></span>
                </li>
              </ol>
            </div>
            <div className="relative ml-11 mt-[-34px] rounded-2xl border border-line bg-surface px-5 py-[18px] shadow-[0_24px_50px_-24px_rgba(14,14,16,0.3)]">
              <div className="flex flex-wrap items-center justify-between gap-2.5">
                <span className="text-xs font-medium uppercase tracking-[0.08em] text-muted">{t('land.pv.receipt')}</span>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-ok-soft px-2.5 py-0.5 text-xs font-medium text-ok"><span className="h-1.5 w-1.5 rounded-full bg-ok" /> {t('land.pv.verified')}</span>
              </div>
              <div className="mt-3.5 flex flex-col gap-2" aria-hidden="true">
                <span className="h-2 w-2/5 rounded bg-line" /><span className="h-2 w-3/4 rounded bg-wash" /><span className="h-2 w-1/2 rounded bg-wash" />
                <span className="mt-2 flex items-end justify-between gap-3"><span className="font-mono text-xs text-muted">LR/MH20/26-27/000123</span><span className="border-b border-line text-xl italic text-muted">A. Mehta</span></span>
              </div>
              <div className="mt-3 text-xs text-muted">{t('land.pv.illus')}</div>
            </div>
          </div>
        </div>

        <div className={`${wrap} flex items-end gap-3 pb-3`} aria-hidden="true">
          <span className="text-left"><span className="block text-xs font-medium uppercase tracking-[0.08em] text-muted">{t('land.route.pickup')}</span><span className="text-sm font-semibold sm:text-base">Chhatrapati Sambhajinagar</span></span>
          <span className="mb-2 flex-1 border-t-[3px] border-dotted border-accent" />
          <span className="text-right"><span className="block text-xs font-medium uppercase tracking-[0.08em] text-muted">{t('land.route.delivery')}</span><span className="text-sm font-semibold sm:text-base">Pune</span></span>
        </div>
        <RoadScene />
      </section>

      <main>
        <section className={`${wrap} py-8`} aria-label="CargoOne">
          <ul className="flex flex-wrap justify-between gap-x-10 gap-y-5">
            {FACTS.map(({ icon: Icon, key }) => (
              <li key={key} className="flex items-center gap-3 text-[15px] font-medium">
                <span className="grid h-[42px] w-[42px] shrink-0 place-items-center rounded-xl border border-line"><Icon size={20} aria-hidden /></span>
                {t(`land.${key}`)}
              </li>
            ))}
          </ul>
        </section>

        <section id="how" className={`${wrap} pb-6 pt-24`} aria-labelledby="how-h">
          <span className={eyebrow}>{t('land.how')}</span>
          <h2 id="how-h" className={`${h2} max-w-2xl`}>{t('land.how.title')}</h2>
          <ol className="mt-12 flex flex-wrap gap-5">
            <li className={card}>
              <span className="font-mono text-sm text-accent">01</span>
              <h3 className="text-2xl font-semibold tracking-tight">{t('land.s1.t')}</h3>
              <p className="text-base leading-relaxed text-muted">{t('land.s1.b')}</p>
              <div className="mt-auto flex flex-wrap gap-2 pt-3" aria-hidden="true">{FORM_CHIPS.map((k) => <span key={k} className={chip}>{t(`land.${k}`)}</span>)}</div>
            </li>
            <li className={card}>
              <span className="font-mono text-sm text-accent">02</span>
              <h3 className="text-2xl font-semibold tracking-tight">{t('land.s2.t')}</h3>
              <p className="text-base leading-relaxed text-muted">{t('land.s2.b')}</p>
              <div className="mt-auto pt-3" aria-hidden="true">
                <span className="inline-flex items-center gap-2 rounded-[14px] rounded-bl bg-ok-soft px-3.5 py-2.5 text-[13px] text-ok"><MessageCircle size={16} /> {t('land.c.accepted')}</span>
              </div>
            </li>
            <li className={card}>
              <span className="font-mono text-sm text-accent">03</span>
              <h3 className="text-2xl font-semibold tracking-tight">{t('land.s3.t')}</h3>
              <p className="text-base leading-relaxed text-muted">{t('land.s3.b')}</p>
              <div className="mt-auto flex flex-wrap gap-2 pt-3" aria-hidden="true">
                <span className="rounded-full bg-accent-soft px-3 py-1 text-[13px] font-medium text-accent">{t('land.c.follow')}</span>
                <span className="rounded-full bg-ok-soft px-3 py-1 text-[13px] font-medium text-ok">{t('land.c.receipt')}</span>
              </div>
            </li>
          </ol>
        </section>

        <section id="why" className={`${wrap} flex flex-wrap items-start gap-x-16 gap-y-12 pb-6 pt-24`} aria-labelledby="why-h">
          <div className="min-w-0 max-w-[440px] flex-[1_1_320px]">
            <span className={eyebrow}>{t('land.why')}</span>
            <h2 id="why-h" className={h2}>{t('land.why.title')}</h2>
            <p className="mt-5 text-[17px] leading-relaxed text-muted">{t('land.why.sub')}</p>
          </div>
          <ul className="flex min-w-0 flex-[2_1_520px] flex-wrap gap-4">
            {BENEFITS.map((k) => (
              <li key={k} id={k === 'w3' ? 'languages' : undefined} className="min-w-0 flex-[1_1_240px] rounded-[18px] border border-line bg-wash p-7">
                <h3 className="text-xl font-semibold tracking-tight">{t(`land.${k}.t`)}</h3>
                <p className="mt-2.5 text-[15.5px] leading-relaxed text-muted">{t(`land.${k}.b`)}</p>
                {k === 'w3' && <div className="mt-4 flex flex-wrap gap-2">{LANGUAGES.map(([v, label]) => <span key={v} className="rounded-full border border-line bg-surface px-3.5 py-1 text-sm">{label}</span>)}</div>}
              </li>
            ))}
          </ul>
        </section>

        <section className={`${wrap} py-24`}>
          <div className="flex flex-col items-center gap-5 overflow-hidden rounded-[28px] bg-ink px-6 pt-[72px] text-center text-surface">
            <h2 className="text-[clamp(2rem,4.4vw,3rem)] font-semibold leading-[1.08] tracking-[-0.03em]">{t('land.finalTitle')}</h2>
            <p className="max-w-md text-[17px] leading-relaxed opacity-75">{t('land.finalBody')}</p>
            <Link to="/request" className="mt-2 inline-flex items-center gap-2.5 rounded-xl bg-surface px-7 py-4 text-base font-medium text-ink hover:opacity-90">{t('land.request')} <ArrowRight size={18} aria-hidden /></Link>
            <div className="relative -mx-6 mt-9 h-[120px] self-stretch overflow-hidden" aria-hidden="true">
              <div className="absolute inset-x-0 bottom-0 h-[30px] bg-surface/10" />
              <div className="absolute inset-x-0 bottom-3.5 border-t-[3px] border-dashed border-surface/40" />
              <svg viewBox="0 0 520 170" className="absolute bottom-2 left-1/2 h-[82px] w-[250px] -translate-x-1/2">
                <TruckArt body="var(--color-ink)" line="var(--color-surface)" cab="var(--color-muted)" glass="var(--scene-window)" label="var(--color-surface)" />
              </svg>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className={`${wrap} flex flex-wrap items-center justify-between gap-3 py-7 text-sm text-muted`}>
          <span>{t('land.privacy')}</span>
          <span className="flex gap-5"><Link to="/privacy" className="underline underline-offset-2">{t('priv.link')}</Link><Link to="/login" className="underline underline-offset-2">{t('land.signIn')}</Link></span>
        </div>
      </footer>
    </div>
  )
}
