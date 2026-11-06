import { X } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api, ApiError, type Invoice } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'

interface Pay { id: string; amount: number; paid_on: string; reference: string | null }
const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })
const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 10)

/** Money received against one invoice. The last payment that covers the total closes the invoice's trips; only an admin can undo a payment, with a reason. */
export function PaymentsDialog({ invoice, onClose, onChanged }: { invoice: Invoice; onClose: () => void; onChanged: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const { t, date } = useI18n()
  const { user } = useAuth()
  const [inv, setInv] = useState(invoice)
  const [rows, setRows] = useState<Pay[]>([])
  const [amount, setAmount] = useState(String(invoice.balance))
  const [paidOn, setPaidOn] = useState(today())
  const [ref_, setRef] = useState('')
  const [undoing, setUndoing] = useState<string | null>(null)
  const [why, setWhy] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = () => api<Pay[]>(`/billing/invoices/${inv.id}/payments`).then(setRows).catch(() => undefined)
  useEffect(() => { ref.current?.showModal(); void load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      const next = await api<Invoice>(`/billing/invoices/${inv.id}/payments`, { method: 'POST', body: JSON.stringify({ amount, paid_on: paidOn, reference: ref_ || null }) })
      setInv(next); setAmount(String(next.balance)); setRef(''); await load(); onChanged()
    } catch (err) { setError(err instanceof ApiError ? err.message : t('sh.failed')) } finally { setBusy(false) }
  }

  async function undo(id: string) {
    setBusy(true); setError(null)
    try {
      const next = await api<Invoice>(`/billing/invoices/${inv.id}/payments/${id}/void`, { method: 'POST', body: JSON.stringify({ reason: why }) })
      setInv(next); setAmount(String(next.balance)); setUndoing(null); setWhy(''); await load(); onChanged()
    } catch (err) { setError(err instanceof ApiError ? err.message : t('sh.failed')) } finally { setBusy(false) }
  }

  const field = 'h-11 w-full rounded-lg border border-line bg-surface px-3.5 text-sm outline-none focus:border-ink'
  return (
    <dialog ref={ref} onClose={onClose} aria-label={t('bill.payTitle', { no: inv.invoice_no })} className="m-auto max-h-[92vh] w-[min(32rem,94vw)] overflow-y-auto rounded-2xl border border-line bg-surface p-0 text-ink shadow-xl backdrop:bg-black/30">
      <div className="space-y-5 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">{t('bill.payTitle', { no: inv.invoice_no })}</h2>
            <p className="text-sm text-muted">{inv.client} · {inr.format(inv.total)}</p>
          </div>
          <button onClick={() => ref.current?.close()} aria-label={t('common.close')} className="text-muted hover:text-ink"><X size={20} /></button>
        </div>

        {rows.length === 0 ? <p className="text-sm text-muted">{t('bill.noPay')}</p> : (
          <ul className="divide-y divide-line rounded-xl border border-line text-sm">
            {rows.map((p) => (
              <li key={p.id} className="space-y-2 px-3 py-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span><b className="tabular-nums">{inr.format(p.amount)}</b> <span className="text-muted">· {date(p.paid_on)}{p.reference ? ` · ${p.reference}` : ''}</span></span>
                  {user?.role === 'admin' && undoing !== p.id && <button onClick={() => setUndoing(p.id)} className="text-xs text-bad underline underline-offset-2">{t('bill.undo')}</button>}
                </div>
                {undoing === p.id && (
                  <div className="flex gap-2">
                    <input aria-label={t('bill.undoWhy')} placeholder={t('bill.undoWhy')} maxLength={200} value={why} onChange={(e) => setWhy(e.target.value)} className={field} />
                    <button disabled={busy || why.trim().length < 3} onClick={() => void undo(p.id)} className="rounded-lg bg-bad px-3 text-sm text-on-solid disabled:opacity-50">{t('bill.undo')}</button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}

        {inv.paid_at ? <p role="status" className="rounded-xl bg-ok-soft px-4 py-3 text-sm font-medium text-ok">{t('bill.closedNote')}</p> : (
          <form onSubmit={(e) => void save(e)} className="space-y-3">
            <p className="text-sm font-medium">{t('bill.balance', { n: inv.balance.toLocaleString('en-IN') })}</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block space-y-1.5 text-sm"><span className="font-medium">{t('bill.amount')}</span><input required inputMode="decimal" className={field} value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
              <label className="block space-y-1.5 text-sm"><span className="font-medium">{t('bill.paidOn')}</span><input type="date" required max={today()} className={field} value={paidOn} onChange={(e) => setPaidOn(e.target.value)} /></label>
            </div>
            <label className="block space-y-1.5 text-sm"><span className="font-medium">{t('bill.ref')}</span><input maxLength={80} className={field} value={ref_} onChange={(e) => setRef(e.target.value)} /></label>
            <button disabled={busy} className="rounded-lg bg-ink px-5 py-2 text-sm font-medium text-surface disabled:opacity-60">{t('bill.recordPay')}</button>
          </form>
        )}
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      </div>
    </dialog>
  )
}
