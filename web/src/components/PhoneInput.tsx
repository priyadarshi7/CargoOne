import { useEffect, useId, useRef, useState } from 'react'
import { digitsOf, phoneProblem } from '../lib/phone'
import { useI18n } from '../lib/i18n'

/** An Indian mobile number: a fixed "+91" in front, digits only, checked as you type. The value is the plain 10 digits (what the server stores).
 *  Pasting "+91 98765 43210" works. The browser also refuses to submit the form while the number is wrong. */
export default function PhoneInput({ label, hint, value, onChange, required, autoComplete, className = '' }: {
  label: string; hint?: string; value: string; onChange: (digits: string) => void; required?: boolean; autoComplete?: string; className?: string
}) {
  const { t } = useI18n()
  const id = useId()
  const ref = useRef<HTMLInputElement>(null)
  const [touched, setTouched] = useState(false)
  const problem = phoneProblem(value)
  // "start" is wrong from the first digit; "short" only becomes an error once the person leaves the box
  const shown = problem === 'start' || (problem === 'short' && touched) ? problem : null
  const message = shown ? t(shown === 'start' ? 'phone.start' : 'phone.short') : ''
  useEffect(() => { ref.current?.setCustomValidity(problem ? t(problem === 'start' ? 'phone.start' : 'phone.short') : '') }, [problem, t])
  return (
    <div className={`block space-y-px text-sm ${className}`}>
      <label htmlFor={id} className="block font-medium leading-[18px]">{label}</label>
      <div className={`flex h-11 items-center overflow-hidden rounded-lg border bg-surface focus-within:border-ink ${shown ? 'border-bad' : 'border-line'}`}>
        <span aria-hidden className="flex h-full items-center border-r border-line bg-wash px-3 text-muted tabular-nums">+91</span>
        <input ref={ref} id={id} type="tel" inputMode="numeric" autoComplete={autoComplete ?? 'tel-national'} required={required} value={value} maxLength={16}
          onChange={(e) => onChange(digitsOf(e.target.value))} onBlur={() => setTouched(true)}
          aria-invalid={shown ? true : undefined} aria-describedby={`${id}-note`} placeholder="98765 43210"
          className="h-full min-w-0 flex-1 bg-transparent px-3.5 tabular-nums outline-none" />
      </div>
      <p id={`${id}-note`} aria-live="polite" className={`min-h-4 pt-1 text-xs ${shown ? 'text-bad' : 'text-muted'}`}>{message || hint || ''}</p>
    </div>
  )
}
