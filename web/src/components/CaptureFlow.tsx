import { ArrowLeft, Camera, CircleCheck, CloudOff, Eye, Focus, LoaderCircle, RotateCcw, Send, Sun, SunDim, TriangleAlert, Volume2, type LucideIcon } from 'lucide-react'
import { useRef, useState, type ChangeEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { User } from '../lib/api'
import { compressPhoto } from '../lib/capture/compress'
import { getPosition } from '../lib/capture/geo'
import { checkPhoto, type Problem } from '../lib/capture/quality'
import { acknowledge, enqueue, flush, getItem, type UploadResult } from '../lib/capture/queue'
import { uploadPod } from '../lib/capture/upload'
import { speak } from '../lib/voice'

type Lang = User['language']

type Phase =
  | { kind: 'ready' }
  | { kind: 'working' }
  | { kind: 'quality'; file: File; problem: Problem } // the photo looks bad on the phone itself: retake before it is uploaded
  | { kind: 'result'; result: UploadResult }
  | { kind: 'offline' }
  | { kind: 'error'; key: string }

export interface CaptureFlowProps {
  tripId: string
  linkToken?: string // SMS-link flow (no login)
  destination: string
  lang: Lang
  backTo?: string // where the back arrow goes; omitted on the public SMS page
}

const PROBLEM: Record<Problem, { Icon: LucideIcon; voice: string }> = {
  blurry: { Icon: Focus, voice: 'retake_blurry' },
  dark: { Icon: SunDim, voice: 'retake_dark' },
  glare: { Icon: Sun, voice: 'retake_glare' },
  empty: { Icon: Eye, voice: 'retake_not_pod' },
}
const USE_ANYWAY: Record<Lang, string> = { en: 'Use this photo', hi: 'यही फोटो भेजें', mr: 'हाच फोटो पाठवा' }

/** One screen, one action. Result is a full-screen colour + icon + voice: green = done, amber = retake/review.
 *  Shared by the logged-in driver app and the no-login SMS link page, so both behave identically. */
export function CaptureFlow({ tripId, linkToken, destination, lang, backTo }: CaptureFlowProps) {
  const [phase, setPhase] = useState<Phase>({ kind: 'ready' })
  const input = useRef<HTMLInputElement>(null)

  function show(next: Phase, voiceKey?: string) {
    setPhase(next)
    if (voiceKey) speak(lang, voiceKey)
  }

  async function onPick(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // allow picking again immediately
    if (!file) return
    setPhase({ kind: 'working' })
    const q = await checkPhoto(file) // instant on-phone check; null (cannot decode) just uploads
    if (q && !q.ok) {
      const problem = q.problems[0]
      show({ kind: 'quality', file, problem }, PROBLEM[problem].voice)
      return
    }
    await send(file)
  }

  async function send(file: File) {
    setPhase({ kind: 'working' })
    try {
      const [blob, pos] = await Promise.all([compressPhoto(file), getPosition()])
      const item = await enqueue({
        tripId, linkToken, blob, capturedAt: new Date().toISOString(), lat: pos?.lat ?? null, lng: pos?.lng ?? null,
      })
      await flush(uploadPod).catch(() => undefined)
      const saved = await getItem(item.id)
      if (saved?.status === 'done' && saved.result) {
        await acknowledge(item.id)
        show({ kind: 'result', result: saved.result }, saved.result.voice)
      } else if (saved?.status === 'failed') {
        await acknowledge(item.id)
        show({ kind: 'error', key: 'review' }, 'review')
      } else {
        show({ kind: 'offline' }, 'saved_offline') // safe on device; syncs when the network returns
      }
    } catch {
      show({ kind: 'error', key: 'retake_blurry' }, 'retake_blurry')
    }
  }

  const picker = (
    <input ref={input} type="file" accept="image/*" capture="environment" className="sr-only" onChange={onPick} />
  )
  const trigger = (cls: string, children: ReactNode) => (
    <button onClick={() => input.current?.click()} className={cls}>{children}</button>
  )
  const back = backTo ? (
    <Link to={backTo} aria-label="Back" className="grid h-14 w-14 place-items-center rounded-full bg-surface/70 text-ink">
      <ArrowLeft size={28} aria-hidden />
    </Link>
  ) : null

  if (phase.kind === 'working') {
    return (
      <Screen tone="bg-surface">
        <LoaderCircle size={96} className="animate-spin text-accent" aria-label="Working" />
      </Screen>
    )
  }

  if (phase.kind === 'quality') {
    const { Icon, voice } = PROBLEM[phase.problem]
    return (
      <Screen tone="bg-warn-soft text-warn" top={back}>
        <Icon size={160} aria-label={phase.problem} />
        {picker}
        {trigger('flex h-24 w-full items-center justify-center rounded-3xl bg-warn text-on-solid', <Camera size={48} aria-hidden />)}
        <div className="flex items-center gap-4">
          <button onClick={() => speak(lang, voice)} aria-label="Repeat" className="grid h-16 w-16 place-items-center rounded-full bg-surface/70"><Volume2 size={32} aria-hidden /></button>
          <button onClick={() => void send(phase.file)} className="inline-flex h-16 items-center gap-2 rounded-full bg-surface/70 px-5 text-base font-medium text-ink"><Send size={20} aria-hidden /> {USE_ANYWAY[lang]}</button>
        </div>
      </Screen>
    )
  }

  if (phase.kind === 'result') {
    const r = phase.result
    const ok = r.decision === 'verified'
    const retake = r.decision === 'retake_requested'
    const Icon = ok ? CircleCheck : retake ? RotateCcw : Eye
    return (
      <Screen tone={ok ? 'bg-ok-soft text-ok' : 'bg-warn-soft text-warn'} top={back}>
        <Icon size={160} aria-label={r.decision} />
        {picker}
        {retake && trigger('flex h-24 w-full items-center justify-center gap-3 rounded-3xl bg-warn text-2xl font-semibold text-on-solid', <><Camera size={40} aria-hidden /> {r.retakes_left}</>)}
        <button onClick={() => speak(lang, r.voice)} aria-label="Repeat" className="grid h-16 w-16 place-items-center rounded-full bg-surface/70">
          <Volume2 size={32} aria-hidden />
        </button>
      </Screen>
    )
  }

  if (phase.kind === 'offline') {
    return (
      <Screen tone="bg-accent-soft text-accent" top={back}>
        <div className="relative" role="img" aria-label="Saved, waiting for network">
          <CloudOff size={160} aria-hidden />
          <span className="absolute -bottom-2 -right-2 grid h-16 w-16 place-items-center rounded-full bg-ok text-on-solid">
            <CircleCheck size={40} aria-hidden />
          </span>
        </div>
        <button onClick={() => speak(lang, 'saved_offline')} aria-label="Repeat" className="grid h-16 w-16 place-items-center rounded-full bg-surface/70">
          <Volume2 size={32} aria-hidden />
        </button>
      </Screen>
    )
  }

  if (phase.kind === 'error') {
    return (
      <Screen tone="bg-warn-soft text-warn" top={back}>
        <TriangleAlert size={160} aria-label="Problem" />
        {picker}
        {trigger('flex h-24 w-full items-center justify-center rounded-3xl bg-warn text-on-solid', <Camera size={48} aria-hidden />)}
      </Screen>
    )
  }

  return (
    <Screen tone="bg-surface" top={back}>
      {picker}
      <p className="text-center text-3xl font-semibold">{destination}</p>
      {trigger('grid h-72 w-full place-items-center rounded-[2rem] bg-ink text-surface active:scale-[0.98]', (
        <span className="flex flex-col items-center gap-4 text-2xl font-semibold">
          <Camera size={96} aria-hidden /> POD
        </span>
      ))}
    </Screen>
  )
}

function Screen({ tone, top, children }: { tone: string; top?: ReactNode; children: ReactNode }) {
  return (
    <div className={`flex min-h-full flex-col ${tone}`}>
      <div className="p-4">{top}</div>
      <div className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center gap-8 px-5 pb-12">
        {children}
      </div>
    </div>
  )
}
