export const BASE = import.meta.env.VITE_API_URL ?? '/api'
const TOKEN_KEY = 'cargoone.token'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

export class ApiError extends Error {
  status: number
  detail: unknown // the raw `detail` from the API (an object for clash errors)
  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

/** One readable sentence from whatever shape the API's `detail` has (text, {message}, or a validation list). */
function messageOf(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg).replace(/^Value error, /, '') : '')).filter(Boolean).join('; ') || 'Request failed'
  if (detail && typeof detail === 'object' && 'message' in detail) return String((detail as { message: unknown }).message)
  return 'Request failed'
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
    throw new ApiError(res.status, messageOf(detail), detail)
  }
  if (res.status === 204) return undefined as T // success with no body (delete, consent, ...)
  return res.json() as Promise<T>
}

export type Role = 'driver' | 'billing' | 'ops' | 'md' | 'admin'
export interface User {
  id: string
  name: string
  role: Role
  language: 'en' | 'hi' | 'mr'
  must_change_secret?: boolean
  tracking_consent?: boolean
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
  state: TripState
  planned_start: string | null
  planned_end: string | null
  started_at: string | null
}
export interface DriverTrip extends Trip {
  material: string | null
  weight_tonnes: number | null
  packages: number | null
  consignee_name: string | null
  consignee_phone: string | null
}
export type TripState = 'planned' | 'in_transit' | 'delivered' | 'cancelled'
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

export interface QueueTrip {
  id: string
  trip_code: string
  lr_no: string
  eway_bill_no: string
  destination: string
  freight_amount: number
  delivered_at: string | null
  verified_at: string | null
}
export interface QueueGroup {
  client_id: string
  client: string
  billing_cycle: string
  period_key: string
  period_label: string
  total: number
  oldest_verified_at: string | null
  trips: QueueTrip[]
}
export interface Invoice {
  id: string
  invoice_no: string
  client: string
  period_label: string | null
  total: number
  trip_count: number
  created_at: string
  exported_at: string | null
}

/** Downloads a protected file (needs the Authorization header, so a plain link would not work). */
export async function download(path: string, fallbackName: string): Promise<void> {
  const token = tokenStore.get()
  const res = await fetch(`${BASE}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) throw new ApiError(res.status, 'Download failed')
  const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? fallbackName
  const url = URL.createObjectURL(await res.blob())
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

export interface Dashboard {
  window_days: number
  includes_demo_data: boolean
  kpis: { within_24h_pct: number | null; pod_to_invoice_days: number | null; lost_pct: number | null; trips_in_window: number; eligible_trips: number }
  targets: { within_24h_pct: number; pod_to_invoice_days: number; baseline_pod_to_invoice_days: number; lost_pct: number; baseline_lost_pct: number }
  working_capital: { annual_freight: number; days_saved: number | null; released: number | null; interest_saved_per_year: number | null; interest_rate: number }
  missing: {
    total: number; amount: number; at_risk_amount: number
    buckets: { label: string; count: number }[]
    by_branch: { branch: string; buckets: { label: string; count: number }[] }[]
  }
  pipeline: { awaiting_review: number; ready_to_bill: number; ready_to_bill_amount: number }
  branches: { branch: string; trips: number; within_24h_pct: number | null; pod_to_invoice_days: number | null; lost_pct: number | null; missing: number; missing_amount: number }[]
  trend: { week: string; label: string; within_24h_pct: number | null; pod_to_invoice_days: number | null }[]
  oldest_missing: { trip_code: string; client: string; branch: string; vehicle: string; driver: string | null; age_days: number; freight: number; status: string }[]
}

export interface ImportIssue { row: number; trip_code: string | null; message: string }
export interface ImportReport {
  dry_run: boolean; total: number; created: number; updated: number; unchanged: number; skipped: number
  errors: ImportIssue[]; warnings: ImportIssue[]; new_clients: string[]; new_branches: string[]; new_vehicles: number
}

/** Multipart upload with the session token (api() forces a JSON content type, which breaks file uploads). */
export async function postFile<T>(path: string, file: File): Promise<T> {
  const token = tokenStore.get()
  const form = new FormData()
  form.set('file', file)
  const res = await fetch(`${BASE}${path}`, { method: 'POST', body: form, headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) {
    const detail = await res.json().then((j) => j.detail).catch(() => res.statusText)
    throw new ApiError(res.status, typeof detail === 'string' ? detail : 'Upload failed')
  }
  return res.json() as Promise<T>
}

/** Multipart POST with extra form fields (api() forces a JSON content type, which breaks file uploads). */
export async function postForm<T>(path: string, form: FormData): Promise<T> {
  const token = tokenStore.get()
  const res = await fetch(`${BASE}${path}`, { method: 'POST', body: form, headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) {
    const detail = await res.json().then((j) => j.detail).catch(() => res.statusText)
    throw new ApiError(res.status, messageOf(detail), detail)
  }
  return res.json() as Promise<T>
}
