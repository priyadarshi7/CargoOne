import { BASE, tokenStore } from '../api'
import { PermanentUploadError, type QueuedPod, type UploadResult } from './queue'

/** Sends one queued photo. Throws PermanentUploadError for answers a retry can never change;
 *  any other thrown error (network, 5xx, expired login) leaves the photo queued. */
export async function uploadPod(item: QueuedPod): Promise<UploadResult> {
  const form = new FormData()
  form.set('file', item.blob, 'pod.webp')
  form.set('client_upload_id', item.id)
  form.set('captured_at', item.capturedAt)
  if (item.lat !== null && item.lng !== null) {
    form.set('lat', String(item.lat))
    form.set('lng', String(item.lng))
  }
  // SMS-link photos carry their own bearer secret in the URL; logged-in photos use the session token.
  const token = item.linkToken ? null : tokenStore.get()
  const url = item.linkToken ? `${BASE}/u/${encodeURIComponent(item.linkToken)}/pod` : `${BASE}/trips/${item.tripId}/pod`
  const res = await fetch(url, {
    method: 'POST',
    body: form,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  }) // a network failure rejects here and keeps the photo queued
  if (res.ok) return (await res.json()) as UploadResult
  // 410 (expired/revoked link) is permanent for this photo; the office must send a new link
  const transient = res.status >= 500 || res.status === 401 || res.status === 408 || res.status === 429
  if (transient) throw new Error(`temporary ${res.status}`)
  const detail = await res.json().then((j) => String(j.detail)).catch(() => res.statusText)
  throw new PermanentUploadError(detail)
}
