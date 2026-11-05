import { ScanSearch, RotateCw, ZoomIn, ZoomOut } from 'lucide-react'
import { useEffect, useState } from 'react'
import { fetchBlob } from '../lib/api'
import { useI18n } from '../lib/i18n'

/** Where the AI found something on the photo. x, y, w, h are fractions (0 to 1) of the image from its top-left corner. */
export interface FoundBox { field: string; x: number; y: number; w: number; h: number; text?: string | null; conf?: number | null; source?: string }

export const FIELD_LABEL: Record<string, string> = {
  lr_no: 'rd.lr', delivery_date: 'rd.date', quantity_received: 'rd.qty', remarks: 'rd.remarks', stamp: 'rd.stamp', signature: 'rd.signature',
}

/** Zoom/rotate viewer for the POD photo - the image is the source of truth, so it gets the most room. */
export function ImageViewer({ submissionId, boxes = [], active = null, onActive }: {
  submissionId: string; boxes?: FoundBox[]; active?: string | null; onActive?: (field: string | null) => void
}) {
  const { t } = useI18n()
  const [show, setShow] = useState(true)
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [zoom, setZoom] = useState(1)
  const [turns, setTurns] = useState(0)

  useEffect(() => {
    let objectUrl: string | null = null
    let alive = true
    fetchBlob(`/pods/${submissionId}/image`)
      .then((b) => {
        if (!alive) return
        objectUrl = URL.createObjectURL(b)
        setUrl(objectUrl)
      })
      .catch(() => alive && setFailed(true))
    return () => {
      alive = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [submissionId])

  const btn = 'grid h-9 w-9 place-items-center rounded-lg border border-line bg-surface text-muted hover:text-ink'
  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex gap-2">
        <button className={btn} onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))} aria-label="Zoom out"><ZoomOut size={18} /></button>
        <button className={btn} onClick={() => setZoom((z) => Math.min(4, z + 0.25))} aria-label="Zoom in"><ZoomIn size={18} /></button>
        <button className={btn} onClick={() => setTurns((t) => t + 1)} aria-label="Rotate"><RotateCw size={18} /></button>
        {boxes.length > 0 && (
          <button className={`inline-flex h-9 items-center gap-1.5 rounded-lg border bg-surface px-3 text-sm ${show ? 'border-ink text-ink' : 'border-line text-muted hover:text-ink'}`} onClick={() => setShow((v) => !v)} aria-pressed={show}>
            <ScanSearch size={16} aria-hidden /> {t('rd.boxes')}
          </button>
        )}
        <span className="ml-auto self-center text-xs tabular-nums text-muted">{Math.round(zoom * 100)}%</span>
      </div>
      <div className="min-h-[60vh] flex-1 overflow-auto rounded-xl border border-line bg-wash">
        {failed && <p className="p-6 text-sm text-bad">Image could not be loaded.</p>}
        {!url && !failed && <p className="p-6 text-sm text-muted">Loading image…</p>}
        {url && (
          <div className="relative mx-auto max-w-none transition-transform" style={{ transform: `rotate(${turns * 90}deg)`, width: `${zoom * 100}%`, transformOrigin: 'center' }}>
            <img src={url} alt="Proof of delivery" draggable={false} className="block w-full" />
            {show && boxes.map((b) => {
              const on = active === b.field
              const label = FIELD_LABEL[b.field] ? t(FIELD_LABEL[b.field] as 'rd.lr') : b.field
              return (
                <button key={b.field} type="button" onMouseEnter={() => onActive?.(b.field)} onMouseLeave={() => onActive?.(null)} onFocus={() => onActive?.(b.field)} onBlur={() => onActive?.(null)}
                  aria-label={`${label}${b.text ? `: ${b.text}` : ''}`}
                  style={{ left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.w * 100}%`, height: `${b.h * 100}%` }}
                  className={`absolute rounded-[3px] border-2 ${b.source === 'vlm' ? 'border-dashed' : ''} ${on ? 'z-10 border-accent bg-accent/15' : 'border-accent/70'}`}>
                  <span className={`pointer-events-none absolute -top-5 left-[-2px] whitespace-nowrap rounded-t px-1.5 py-px text-[11px] font-medium leading-4 text-surface ${on ? 'bg-accent' : 'bg-accent/80'}`}>{label}</span>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
