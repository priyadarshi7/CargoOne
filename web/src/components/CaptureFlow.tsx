import { ArrowLeft, Camera, CircleCheck, CloudOff, Eye, LoaderCircle, RotateCcw, TriangleAlert, Volume2 } from 'lucide-react'
import { useRef, useState, type ChangeEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { User } from '../lib/api'
import { compressPhoto } from '../lib/capture/compress'
import { getPosition } from '../lib/capture/geo'
import { acknowledge, enqueue, flush, getItem, type UploadResult } from '../lib/capture/queue'
import { uploadPod } from '../lib/capture/upload'
import { speak } from '../lib/voice'

type Lang = User['language']

type Phase =
  | { kind: 'ready' }
  | { kind: 'working' }
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
    <Link to={backTo} aria-label="Back" className="grid h-14 w-14 place-items-center rounded-full bg-white/70 text-ink">
      <ArrowLeft size={28} aria-hidden />
    </Link>
  ) : null

  if (phase.kind === 'working') {
    return (
      <Screen tone="bg-white">
        <LoaderCircle size={96} className="animate-spin text-accent" aria-label="Working" />
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
        {retake && trigger('flex h-24 w-full items-center justify-center gap-3 rounded-3xl bg-warn text-2xl font-semibold text-white', <><Camera size={40} aria-hidden /> {r.retakes_left}</>)}
        <button onClick={() => speak(lang, r.voice)} aria-label="Repeat" className="grid h-16 w-16 place-items-center rounded-full bg-white/70">
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
          <span className="absolute -bottom-2 -right-2 grid h-16 w-16 place-items-center rounded-full bg-ok text-white">
            <CircleCheck size={40} aria-hidden />
          </span>
        </div>
        <button onClick={() => speak(lang, 'saved_offline')} aria-label="Repeat" className="grid h-16 w-16 place-items-center rounded-full bg-white/70">
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
        {trigger('flex h-24 w-full items-center justify-center rounded-3xl bg-warn text-white', <Camera size={48} aria-hidden />)}
      </Screen>
    )
  }

  return (
    <Screen tone="bg-white" top={back}>
      {picker}
      <p className="text-center text-3xl font-semibold">{destination}</p>
      {trigger('grid h-72 w-full place-items-center rounded-[2rem] bg-accent text-white active:scale-[0.98]', (
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
