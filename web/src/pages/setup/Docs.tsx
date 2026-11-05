import { Eye, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, ApiError, fetchBlob, postForm } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import { btnGhost } from './ui'

export interface Doc { id: string; kind: string; mime: string; size_bytes: number; uploaded_at: string | null }
export const VEHICLE_DOCS = ['rc', 'insurance', 'fitness', 'permit', 'puc'] as const
export const DRIVER_DOCS = ['licence', 'licence_back'] as const
export const TRIP_DOCS = ['lr_scan'] as const
export type DocKind = (typeof VEHICLE_DOCS)[number] | (typeof DRIVER_DOCS)[number] | (typeof TRIP_DOCS)[number]
export type OwnerType = 'vehicle' | 'driver' | 'trip'

/** Phone photos are often 4-8 MB: scale a big image down before it leaves the browser. PDFs and small files go as they are. */
async function shrink(file: File): Promise<File> {
  if (!file.type.startsWith('image/') || file.size <= 1_500_000) return file
  try {
    const bmp = await createImageBitmap(file)
    const scale = Math.min(1, 2000 / Math.max(bmp.width, bmp.height))
    const canvas = Object.assign(document.createElement('canvas'), { width: Math.round(bmp.width * scale), height: Math.round(bmp.height * scale) })
    canvas.getContext('2d')?.drawImage(bmp, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, 'image/jpeg', 0.82))
    return blob ? new File([blob], 'photo.jpg', { type: 'image/jpeg' }) : file
  } catch { return file }
}

export async function uploadDoc(ownerType: OwnerType, ownerId: string, kind: string, file: File): Promise<Doc> {
  const form = new FormData()
  form.set('owner_type', ownerType)
  form.set('owner_id', ownerId)
  form.set('kind', kind)
  form.set('file', await shrink(file))
  return postForm<Doc>('/documents', form)
}

export async function openDoc(id: string): Promise<void> {
  const url = URL.createObjectURL(await fetchBlob(`/documents/${id}/file`))
  window.open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

/** One row per paper kind: shows whether it is on file, and lets the ops head upload, replace, view or remove it. */
export function DocSlots({ ownerType, ownerId, kinds, canEdit }: { ownerType: OwnerType; ownerId: string; kinds: readonly DocKind[]; canEdit: boolean }) {
  const { t } = useI18n()
  const [docs, setDocs] = useState<Doc[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pick = useRef<string>('')
  const input = useRef<HTMLInputElement>(null)
  const load = () => api<Doc[]>(`/documents?owner_type=${ownerType}&owner_id=${ownerId}`).then(setDocs).catch(() => setDocs([]))
  useEffect(() => { void load() }, [ownerId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function chosen(file: File | undefined) {
    if (!file) return
    setBusy(pick.current)
    setError(null)
    try { await uploadDoc(ownerType, ownerId, pick.current, file); await load() }
    catch (e) { setError(e instanceof ApiError ? e.message : t('onb.doc.fail')) } finally { setBusy(null); if (input.current) input.current.value = '' }
  }
  async function remove(d: Doc) {
    setBusy(d.kind)
    try { await api(`/documents/${d.id}`, { method: 'DELETE' }); await load() } finally { setBusy(null) }
  }

  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">{t('onb.docs')}</h3>
      <input ref={input} type="file" accept="image/*,application/pdf" className="hidden" aria-label="file" onChange={(e) => void chosen(e.target.files?.[0])} />
      <ul className="divide-y divide-line rounded-xl border border-line">
        {kinds.map((k) => {
          const d = docs?.find((x) => x.kind === k)
          return (
            <li key={k} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
              <span className="min-w-0 flex-1">{t(`onb.doc.${k}`)}</span>
              <span className={d ? 'text-ok' : 'text-muted'}>{d ? `${Math.max(1, Math.round(d.size_bytes / 1024))} KB` : t('onb.doc.missing')}</span>
              {d && <button type="button" onClick={() => void openDoc(d.id)} className={`${btnGhost} inline-flex items-center gap-1`}><Eye size={14} aria-hidden /> {t('onb.doc.view')}</button>}
              {canEdit && <button type="button" disabled={busy === k} onClick={() => { pick.current = k; input.current?.click() }} className={`${btnGhost} inline-flex items-center gap-1`}><Upload size={14} aria-hidden /> {d ? t('onb.doc.replace') : t('onb.doc.upload')}</button>}
              {canEdit && d && <button type="button" disabled={busy === k} onClick={() => void remove(d)} aria-label={`${t('onb.doc.remove')} ${t(`onb.doc.${k}`)}`} className="text-muted hover:text-bad"><Trash2 size={16} /></button>}
            </li>
          )
        })}
      </ul>
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      <p className="text-xs text-muted">{t('onb.docsHint')}</p>
    </section>
  )
}

/** File pickers shown inside a "new" form, before the record exists. The files are sent right after it is saved. */
export function PendingDocs({ kinds, files, onChange }: { kinds: readonly DocKind[]; files: Record<string, File | undefined>; onChange: (f: Record<string, File | undefined>) => void }) {
  const { t } = useI18n()
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold">{t('onb.docs')}</h3>
      {kinds.map((k) => (
        <label key={k} className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <span>{t(`onb.doc.${k}`)}</span>
          <input type="file" accept="image/*,application/pdf" className="max-w-[60%] text-xs" aria-label={t(`onb.doc.${k}`)} onChange={(e) => onChange({ ...files, [k]: e.target.files?.[0] })} />
        </label>
      ))}
      <p className="text-xs text-muted">{t('onb.docsHint')}</p>
    </div>
  )
}

/** Sends the files picked in a "new" form. A failure is reported but never undoes the record that was just saved. */
export async function uploadPending(ownerType: OwnerType, ownerId: string, files: Record<string, File | undefined>): Promise<string | null> {
  let failed: string | null = null
  for (const [kind, file] of Object.entries(files)) {
    if (!file) continue
    try { await uploadDoc(ownerType, ownerId, kind, file) } catch (e) { failed = e instanceof ApiError ? e.message : null }
  }
  return failed
}
