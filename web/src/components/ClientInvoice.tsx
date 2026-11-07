import { CircleCheck, Clock, FileText, TriangleAlert } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { ApiError } from '../lib/api'
import { useI18n } from '../lib/i18n'

export interface Claim { id: string; amount: number; paid_on: string; reference: string; status: 'pending' | 'confirmed' | 'rejected'; reject_reason: string | null }
export interface InvoiceView {
  id: string; invoice_no: string; period_label: string | null; total: number; sent_at: string; paid_at: string | null
  paid_amount: number; balance: number; claims: Claim[]; payments: { amount: number; paid_on: string; reference: string | null }[]
}
export interface ClaimBody { amount: string; paid_on: string; reference: string; note: string | null }

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })
const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
const field = 'h-11 w-full rounded-lg border border-line bg-surface px-3.5 text-sm outline-none focus:border-ink'

/** One invoice as its client sees it: what is due, what billing has received, the PDF with the proof of delivery, and "I have paid" (billing then checks the bank).
 *  The same card is used on the client's own login and on their private shipment page. */
export function ClientInvoice({ inv, openPdf, claim, onChange }: { inv: InvoiceView; openPdf: () => Promise<Blob>; claim: (b: ClaimBody) => Promise<InvoiceView>; onChange: (v: InvoiceView) => void }) {
  const { t, date } = useI18n()
  const [form, setForm] = useState<{ amount: string; paid_on: string; reference: string; note: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const waiting = inv.claims.filter((c) => c.status === 'pending')
  const status = inv.paid_at ? 'paid' : inv.paid_amount > 0 ? 'part' : 'due'
  const tone = { paid: 'bg-ok-soft text-ok', part: 'bg-warn-soft text-warn', due: 'bg-accent-soft text-accent' }[status]

  async function view() {
    setError(null)
    const tab = window.open('', '_blank') // opened now, filled when the file arrives, so a pop-up blocker lets it through
    try {
      const url = URL.createObjectURL(await openPdf())
      if (tab) tab.location.href = url
      else window.location.href = url
    } catch { tab?.close(); setError(t('inv.openFail')) }
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!form) return
    setBusy(true); setError(null)
    try { onChange(await claim({ amount: form.amount, paid_on: form.paid_on, reference: form.reference, note: form.note.trim() || null })); setForm(null) }
    catch (err) { setError(err instanceof ApiError ? err.message : t('inv.claimFail')) }
    finally { setBusy(false) }
  }

  return (
    <section aria-label={`${t('inv.invoice')} ${inv.invoice_no}`} className="space-y-3 rounded-xl border border-line px-4 py-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-semibold">{t('inv.invoice')} {inv.invoice_no}</p>
          <p className="text-muted">{inv.period_label ? `${inv.period_label} · ` : ''}{t('inv.sentOn', { when: date(inv.sent_at) })}</p>
        </div>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${tone}`}>{t(`inv.st.${status}` as const)}</span>
      </div>
      <dl className="grid grid-cols-3 gap-3">
        <div><dt className="text-muted">{t('inv.total')}</dt><dd className="font-semibold tabular-nums">{inr.format(inv.total)}</dd></div>
        <div><dt className="text-muted">{t('inv.received')}</dt><dd className="font-semibold tabular-nums">{inr.format(inv.paid_amount)}</dd></div>
        <div><dt className="text-muted">{t('inv.balance')}</dt><dd className="font-semibold tabular-nums">{inr.format(inv.balance)}</dd></div>
      </dl>

      {inv.claims.length > 0 && (
        <ul className="space-y-1.5">
          {inv.claims.map((c) => (
            <li key={c.id} className={`flex items-start gap-2 rounded-lg px-3 py-2 ${c.status === 'rejected' ? 'bg-bad-soft text-bad' : c.status === 'confirmed' ? 'bg-ok-soft text-ok' : 'bg-wash text-muted'}`}>
              {c.status === 'confirmed' ? <CircleCheck size={16} className="mt-0.5 shrink-0" aria-hidden /> : c.status === 'rejected' ? <TriangleAlert size={16} className="mt-0.5 shrink-0" aria-hidden /> : <Clock size={16} className="mt-0.5 shrink-0" aria-hidden />}
              <span><span className="font-medium tabular-nums">{inr.format(c.amount)}</span> · {c.reference} · {date(c.paid_on)}<span className="block">{c.status === 'rejected' ? t('inv.c.rejected', { why: c.reject_reason ?? '' }) : t(`inv.c.${c.status}` as const)}</span></span>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => void view()} className="inline-flex h-10 items-center gap-2 rounded-lg border border-line px-3.5 font-medium hover:border-ink hover:bg-wash"><FileText size={16} aria-hidden /> {t('inv.view')}</button>
        {!inv.paid_at && !form && waiting.length < 3 && (
          <button type="button" onClick={() => setForm({ amount: String(inv.balance), paid_on: today(), reference: '', note: '' })} className="h-10 rounded-lg bg-ink px-3.5 font-medium text-surface hover:opacity-90">{t('inv.pay')}</button>
        )}
      </div>

      {form && (
        <form onSubmit={(e) => void submit(e)} className="space-y-3 rounded-xl bg-wash p-3">
          <p className="text-muted">{t('inv.tellHelp')}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block space-y-1"><span className="font-medium">{t('inv.amount')}</span><input className={field} required inputMode="decimal" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value.replace(/[^\d.]/g, '') })} /></label>
            <label className="block space-y-1"><span className="font-medium">{t('inv.date')}</span><input className={field} type="date" required max={today()} value={form.paid_on} onChange={(e) => setForm({ ...form, paid_on: e.target.value })} /></label>
          </div>
          <label className="block space-y-1"><span className="font-medium">{t('inv.ref')}</span><input className={field} required minLength={3} maxLength={80} value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} /></label>
          <label className="block space-y-1"><span className="font-medium">{t('inv.note')}</span><input className={field} maxLength={200} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
          <div className="flex gap-2">
            <button disabled={busy} className="h-10 rounded-lg bg-ink px-4 font-medium text-surface hover:opacity-90 disabled:opacity-60">{busy ? t('common.loading') : t('inv.tell')}</button>
            <button type="button" onClick={() => { setForm(null); setError(null) }} className="h-10 rounded-lg px-3 text-muted hover:text-ink">{t('common.cancel')}</button>
          </div>
        </form>
      )}
      {error && <p role="alert" className="text-bad">{error}</p>}
    </section>
  )
}
