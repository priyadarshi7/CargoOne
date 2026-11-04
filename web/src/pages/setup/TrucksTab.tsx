import { Pencil, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import type { VendorRef } from './DriversTab'
import { btnGhost, btnPrimary, Field, FormModal, inputCls, StatusPill, Table } from './ui'

interface Truck {
  id: string; reg_no: string; is_hired: boolean; vendor_id: string | null; vendor: string | null; vehicle_type: string | null; capacity_tonnes: number | null
  insurance_expiry: string | null; fitness_expiry: string | null; permit_expiry: string | null; is_active: boolean; papers: 'ok' | 'due_soon' | 'expired' | null
}
const PAPER_CLS = { ok: 'text-ok', due_soon: 'text-warn', expired: 'text-bad' } as const

export default function TrucksTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useI18n()
  const [rows, setRows] = useState<Truck[] | null>(null)
  const [vendors, setVendors] = useState<VendorRef[]>([])
  const [error, setError] = useState(false)
  const [showOff, setShowOff] = useState(false)
  const [form, setForm] = useState<Truck | 'new' | null>(null)
  const load = () => api<Truck[]>('/setup/vehicles').then(setRows).catch(() => setError(true))
  useEffect(() => { void load(); api<VendorRef[]>('/setup/vendors').then(setVendors).catch(() => undefined) }, [])
  if (error) return <p className="text-bad">{t('setup.loadFail')}</p>
  if (!rows) return <p className="text-muted">{t('common.loading')}</p>
  const shown = rows.filter((v) => showOff || v.is_active)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={showOff} onChange={(e) => setShowOff(e.target.checked)} /> {t('setup.showInactive')}</label>
        {canEdit && <button onClick={() => setForm('new')} className={`${btnPrimary} inline-flex items-center gap-1.5`}><Plus size={16} aria-hidden /> {t('setup.truck.add')}</button>}
      </div>
      <Table head={[t('setup.truck.reg'), t('setup.truck.type'), t('setup.truck.owner'), t('setup.truck.papers'), t('drv.status'), '']} empty={shown.length ? undefined : t('setup.none')}>
        {shown.map((v) => (
          <tr key={v.id} className={`border-t border-line ${v.is_active ? '' : 'text-muted'}`}>
            <td className="px-4 py-3 font-medium tabular-nums">{v.reg_no}</td>
            <td className="px-4 py-3">{[v.vehicle_type, v.capacity_tonnes ? `${v.capacity_tonnes} t` : null].filter(Boolean).join(' · ') || '—'}</td>
            <td className="px-4 py-3">{v.is_hired ? [t('setup.hired'), v.vendor].filter(Boolean).join(' · ') : t('setup.own')}</td>
            <td className={`px-4 py-3 ${v.papers ? PAPER_CLS[v.papers] : 'text-muted'}`}>{v.papers ? t(`setup.truck.${v.papers}`) : '—'}</td>
            <td className="px-4 py-3"><StatusPill active={v.is_active} /></td>
            <td className="px-4 py-3 text-right">{canEdit && <button onClick={() => setForm(v)} className={`${btnGhost} inline-flex items-center gap-1.5`}><Pencil size={14} aria-hidden /> {t('setup.edit')}</button>}</td>
          </tr>
        ))}
      </Table>
      {form && <TruckForm truck={form === 'new' ? null : form} vendors={vendors.filter((v) => v.is_active)} onClose={() => setForm(null)} onSaved={() => { setForm(null); void load() }} />}
    </div>
  )
}

function TruckForm({ truck, vendors, onClose, onSaved }: { truck: Truck | null; vendors: VendorRef[]; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n()
  const [f, setF] = useState({
    reg_no: truck?.reg_no ?? '', vehicle_type: truck?.vehicle_type ?? '', capacity_tonnes: truck?.capacity_tonnes?.toString() ?? '',
    insurance_expiry: truck?.insurance_expiry ?? '', fitness_expiry: truck?.fitness_expiry ?? '', permit_expiry: truck?.permit_expiry ?? '', vendor_id: truck?.vendor_id ?? '',
    is_active: truck?.is_active ?? true,
  })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  async function save() {
    const body = JSON.stringify({
      reg_no: f.reg_no, vehicle_type: f.vehicle_type || null, capacity_tonnes: f.capacity_tonnes || null, insurance_expiry: f.insurance_expiry || null,
      fitness_expiry: f.fitness_expiry || null, permit_expiry: f.permit_expiry || null, vendor_id: f.vendor_id || null, ...(truck ? { is_active: f.is_active } : {}),
    })
    await api(truck ? `/setup/vehicles/${truck.id}` : '/setup/vehicles', { method: truck ? 'PATCH' : 'POST', body })
    onSaved()
  }
  return (
    <FormModal title={truck ? truck.reg_no : t('setup.truck.add')} onClose={onClose} onSubmit={save}>
      <Field label={t('setup.truck.reg')} hint="MH20 AB 1234"><input className={inputCls} required value={f.reg_no} onChange={set('reg_no')} /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label={t('setup.truck.type')}><input className={inputCls} value={f.vehicle_type} onChange={set('vehicle_type')} placeholder="Container 32 ft" /></Field>
        <Field label={t('setup.truck.capacity')}><input className={inputCls} inputMode="decimal" value={f.capacity_tonnes} onChange={set('capacity_tonnes')} /></Field>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Field label={t('setup.truck.insurance')}><input type="date" className={inputCls} value={f.insurance_expiry} onChange={set('insurance_expiry')} /></Field>
        <Field label={t('setup.truck.fitness')}><input type="date" className={inputCls} value={f.fitness_expiry} onChange={set('fitness_expiry')} /></Field>
        <Field label={t('setup.truck.permit')}><input type="date" className={inputCls} value={f.permit_expiry} onChange={set('permit_expiry')} /></Field>
      </div>
      <Field label={t('setup.truck.owner')}>
        <select className={inputCls} value={f.vendor_id} onChange={set('vendor_id')}>
          <option value="">{t('setup.own')}</option>
          {vendors.map((v) => <option key={v.id} value={v.id}>{t('setup.hired')} · {v.name}</option>)}
        </select>
      </Field>
      {truck && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> {t('setup.active')}</label>}
    </FormModal>
  )
}
