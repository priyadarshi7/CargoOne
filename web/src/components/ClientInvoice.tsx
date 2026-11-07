import { FileText } from 'lucide-react'
import { useState } from 'react'
import { ApiError } from '../lib/api'
import { useI18n } from '../lib/i18n'

export interface InvoiceView {
  id: string; invoice_no: string; period_label: string | null; total: number; sent_at: string; paid_at: string | null
  paid_amount: number; balance: number; can_pay_online: boolean; payments: { amount: number; paid_on: string; reference: string | null }[]
}
export interface Checkout { key_id: string; order_id: string; amount: number; currency: string; name: string; description: string; prefill_name: string }
export interface Returned { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }
export interface OnlinePay { start: () => Promise<Checkout>; confirm: (r: Returned) => Promise<InvoiceView> }

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })

type RazorpayCtor = new (o: Record<string, unknown>) => { open: () => void; on: (e: string, f: () => void) => void }
function loadCheckout(): Promise<RazorpayCtor> {
  const have = (window as unknown as { Razorpay?: RazorpayCtor }).Razorpay
  if (have) return Promise.resolve(have)
  return new Promise((ok, no) => {
    const s = document.createElement('script')
    s.src = 'https://checkout.razorpay.com/v1/checkout.js'
    s.onload = () => ok((window as unknown as { Razorpay: RazorpayCtor }).Razorpay)
    s.onerror = () => no(new Error('checkout'))
    document.head.appendChild(s)
  })
}

/** One invoice as its client sees it: what is due, what billing has received, the PDF with the proof of delivery, and Pay online (Razorpay) when it is set up.
 *  Money paid any other way (cash, a transfer) is recorded by billing and simply appears here. The same card is used on the client's login and on their private shipment page. */
export function ClientInvoice({ inv, openPdf, online, onChange }: { inv: InvoiceView; openPdf: () => Promise<Blob>; online?: OnlinePay; onChange: (v: InvoiceView) => void }) {
  const { t, date } = useI18n()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
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

  async function payNow() {
    if (!online) return
    setBusy(true); setError(null); setNotice(null)
    try {
      const [Razorpay, order] = await Promise.all([loadCheckout(), online.start()])
      const box = new Razorpay({
        key: order.key_id, order_id: order.order_id, amount: order.amount, currency: order.currency, name: order.name, description: order.description, prefill: { name: order.prefill_name },
        handler: (r: Returned) => {
          void online.confirm(r).then((v) => { onChange(v); setNotice(t('inv.paidOnline')) })
            .catch(() => setNotice(t('inv.paidCheck'))) // the money moved; the page just could not hear back, and billing's side catches up on its own
            .finally(() => setBusy(false))
        },
        modal: { ondismiss: () => setBusy(false) },
      })
      box.on('payment.failed', () => setError(t('inv.payFailed')))
      box.open()
    } catch (err) { setBusy(false); setError(err instanceof ApiError ? err.message : t('inv.payUnavailable')) }
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

      {inv.payments.length > 0 && (
        <ul className="space-y-1 text-muted">
          {inv.payments.map((p, i) => <li key={i}><span className="font-medium tabular-nums text-ink">{inr.format(p.amount)}</span> · {date(p.paid_on)}{p.reference ? ` · ${p.reference}` : ''}</li>)}
        </ul>
      )}

      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => void view()} className="inline-flex h-10 items-center gap-2 rounded-lg border border-line px-3.5 font-medium hover:border-ink hover:bg-wash"><FileText size={16} aria-hidden /> {t('inv.view')}</button>
        {online && inv.can_pay_online && (
          <button type="button" disabled={busy} onClick={() => void payNow()} className="h-10 rounded-lg bg-ink px-3.5 font-medium text-surface hover:opacity-90 disabled:opacity-60">{busy ? t('common.loading') : t('inv.payOnline', { amount: inr.format(inv.balance) })}</button>
        )}
      </div>
      {notice && <p role="status" className="text-ok">{notice}</p>}
      {error && <p role="alert" className="text-bad">{error}</p>}
    </section>
  )
}
