import { Monitor, Moon, Sun, type LucideIcon } from 'lucide-react'
import { useI18n } from '../lib/i18n'
import { useTheme, type Theme } from '../lib/theme'

const NEXT: Record<Theme, Theme> = { system: 'light', light: 'dark', dark: 'system' }
const ICON: Record<Theme, LucideIcon> = { system: Monitor, light: Sun, dark: Moon }
const ORDER: Theme[] = ['light', 'system', 'dark']

/** One small button that cycles auto, light, dark. Used in every header (landing, sign-in, public pages, office). */
export function ThemeToggle({ className = '' }: { className?: string }) {
  const { theme, setTheme } = useTheme()
  const Icon = ICON[theme]
  return (
    <button onClick={() => setTheme(NEXT[theme])} aria-label={`Theme: ${theme}`} title={`Theme: ${theme}`}
      className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-line text-muted hover:text-ink ${className}`}>
      <Icon size={18} aria-hidden />
    </button>
  )
}

/** Three big choices (for the driver's Help screen): the colour is chosen by pressing a picture, not by reading a setting. */
export function ThemeChoice() {
  const { t } = useI18n()
  const { theme, setTheme } = useTheme()
  return (
    <div role="group" aria-label={t('theme.label')} className="grid grid-cols-3 gap-2">
      {ORDER.map((x) => {
        const Icon = ICON[x]
        return (
          <button key={x} onClick={() => setTheme(x)} aria-pressed={theme === x}
            className={`flex min-h-20 flex-col items-center justify-center gap-1.5 rounded-2xl border text-sm font-semibold ${theme === x ? 'border-ink bg-ink text-surface' : 'border-line text-muted'}`}>
            <Icon size={26} aria-hidden /> {t(`theme.${x}`)}
          </button>
        )
      })}
    </div>
  )
}
