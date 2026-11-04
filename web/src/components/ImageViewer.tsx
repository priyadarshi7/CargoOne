import { RotateCw, ZoomIn, ZoomOut } from 'lucide-react'
import { useEffect, useState } from 'react'
import { fetchBlob } from '../lib/api'

/** Zoom/rotate viewer for the POD photo - the image is the source of truth, so it gets the most room. */
export function ImageViewer({ submissionId }: { submissionId: string }) {
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

  const btn = 'grid h-9 w-9 place-items-center rounded-lg border border-line bg-white text-muted hover:text-ink'
  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex gap-2">
        <button className={btn} onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))} aria-label="Zoom out"><ZoomOut size={18} /></button>
        <button className={btn} onClick={() => setZoom((z) => Math.min(4, z + 0.25))} aria-label="Zoom in"><ZoomIn size={18} /></button>
        <button className={btn} onClick={() => setTurns((t) => t + 1)} aria-label="Rotate"><RotateCw size={18} /></button>
        <span className="ml-auto self-center text-xs tabular-nums text-muted">{Math.round(zoom * 100)}%</span>
      </div>
      <div className="min-h-[60vh] flex-1 overflow-auto rounded-xl border border-line bg-wash">
        {failed && <p className="p-6 text-sm text-bad">Image could not be loaded.</p>}
        {!url && !failed && <p className="p-6 text-sm text-muted">Loading image…</p>}
        {url && (
          <img src={url} alt="Proof of delivery" draggable={false}
            style={{ transform: `rotate(${turns * 90}deg)`, width: `${zoom * 100}%`, transformOrigin: 'center' }}
            className="mx-auto block max-w-none transition-transform" />
        )}
      </div>
    </div>
  )
}
