export const BASE = import.meta.env.VITE_API_URL ?? '/api'
const TOKEN_KEY = 'cargoone.token'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenStore.get()
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  })
  if (!res.ok) {
    const detail = await res.json().then((j) => j.detail).catch(() => res.statusText)
    throw new ApiError(res.status, typeof detail === 'string' ? detail : 'Request failed')
  }
  return res.json() as Promise<T>
}

export type Role = 'driver' | 'billing' | 'ops' | 'md' | 'admin'
export interface User {
  id: string
  name: string
  role: Role
  language: 'en' | 'hi' | 'mr'
}
export interface Trip {
  id: string
  trip_code: string
  client: string
  vehicle: string
  is_hired: boolean
  branch: string | null
  lr_no: string
  eway_bill_no: string
  origin: string
  destination: string
  freight_amount: number
  pod_status: PodStatus
  retake_count: number
  delivered_at: string | null
}
export type PodStatus =
  | 'pending' | 'uploaded' | 'verified' | 'needs_review' | 'retake_requested' | 'rejected' | 'billed'

export interface ReviewItem {
  trip_id: string
  trip_code: string
  client: string
  lr_no: string
  destination: string
  freight_amount: number
  submission_id: string
  attempt: number
  reasons: string[]
  confidence: number | null
  ai: Record<string, unknown>
  corrected: Record<string, unknown> | null
  captured_at: string
  lat: number | null
  lng: number | null
  retakes_left: number
}

/** Fetches a protected file (the POD image needs the Authorization header, so <img src> cannot be used). */
export async function fetchBlob(path: string): Promise<Blob> {
  const token = tokenStore.get()
  const res = await fetch(`${BASE}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) throw new ApiError(res.status, 'Could not load image')
  return res.blob()
}
