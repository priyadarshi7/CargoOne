import { useCallback, useEffect, useState } from 'react'
import { api } from './api'

/** Alerts that reach the phone even when the app is closed (Web Push). The browser asks the person once; we then give it our
 *  public key and keep the address it returns. Not available on every phone, so every function says so instead of failing. */
export const pushSupported = (): boolean =>
  typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window

/** The server's public key arrives as URL-safe base64; the browser wants raw bytes. */
export function keyBytes(b64: string): Uint8Array<ArrayBuffer> {
  const pad = '='.repeat((4 - (b64.length % 4)) % 4)
  const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'))
  const out = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

export type PushState = 'unsupported' | 'blocked' | 'off' | 'on' | 'no-server'

async function registration(): Promise<ServiceWorkerRegistration | null> {
  try { return (await navigator.serviceWorker.getRegistration()) ?? null } catch { return null } // no worker (development build): alerts cannot work
}

async function current(): Promise<PushState> {
  if (!pushSupported()) return 'unsupported'
  if (Notification.permission === 'denied') return 'blocked'
  const reg = await registration()
  if (!reg) return 'unsupported'
  const sub = await reg.pushManager.getSubscription()
  return sub && Notification.permission === 'granted' ? 'on' : 'off'
}

/** Turn alerts on for this phone. Returns the new state; asks for permission at the moment of the tap. */
export async function enablePush(): Promise<PushState> {
  if (!pushSupported()) return 'unsupported'
  const { key } = await api<{ key: string | null; live: boolean }>('/push/key')
  if (!key) return 'no-server'
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') return permission === 'denied' ? 'blocked' : 'off'
  const reg = await registration()
  if (!reg) return 'unsupported'
  const sub = (await reg.pushManager.getSubscription()) ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) }))
  const json = sub.toJSON()
  await api('/push/subscribe', { method: 'POST', body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }) })
  return 'on'
}

export async function disablePush(): Promise<PushState> {
  const reg = await registration()
  const sub = reg ? await reg.pushManager.getSubscription() : null
  if (sub) {
    await api('/push/unsubscribe', { method: 'POST', body: JSON.stringify({ endpoint: sub.endpoint }) }).catch(() => undefined)
    await sub.unsubscribe().catch(() => undefined)
  }
  return current()
}

export function usePush(): { state: PushState | null; enable: () => Promise<void>; disable: () => Promise<void>; refresh: () => void } {
  const [state, setState] = useState<PushState | null>(null)
  const refresh = useCallback(() => { void current().then(setState) }, [])
  useEffect(refresh, [refresh])
  return {
    state, refresh,
    enable: async () => { try { setState(await enablePush()) } catch { setState('off') } },
    disable: async () => { setState(await disablePush()) },
  }
}
