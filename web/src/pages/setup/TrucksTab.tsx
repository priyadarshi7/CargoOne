import { Eye, Pencil, Plus } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { api } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import type { VendorRef } from './DriversTab'
import { DocSlots, PendingDocs, uploadPending, VEHICLE_DOCS } from './Docs'
import { btnGhost, btnPrimary, Facts, Field, FormModal, inputCls, Modal, StatusPill, Table } from './ui'

export interface Truck {
  id: string; reg_no: string; is_hired: boolean; vendor_id: string | null; vendor: string | null; owner_name: string | null; vehicle_type: string | null
  capacity_tonnes: number | null; rc_no: string | null; registration_date: string | null; chassis_no: string | null; engine_no: string | null; insurance_no: string | null
  insurance_expiry: string | null; fitness_expiry: string | null; permit_expiry: string | null; puc_expiry: string | null
  availability: 'available' | 'maintenance' | 'breakdown'; availability_note: string | null; is_active: boolean; papers: 'ok' | 'due_soon' | 'expired' | null
}
const PAPER_CLS = { ok: 'text-ok', due_soon: 'text-warn', expired: 'text-bad' } as const
const AVAIL_CLS = { available: 'text-ok', maintenance: 'text-warn', breakdown: 'text-bad' } as const
const EXPIRIES = [['insurance_expiry', 'setup.truck.insurance'], ['fitness_expiry', 'setup.truck.fitness'], ['permit_expiry', 'setup.truck.permit'], ['puc_expiry', 'onb.truck.puc']] as const

function dayState(d: string | null): keyof typeof PAPER_CLS | null {
  if (!d) return null
  const days = Math.floor((new Date(d).getTime() - Date.now()) / 86_400_000)
  return days < 0 ? 'expired' : days <= 30 ? 'due_soon' : 'ok'
}

export default function TrucksTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useI18n()
  const [rows, setRows] = useState<Truck[] | null>(null)
  const [vendors, setVendors] = useState<VendorRef[]>([])
  const [error, setError] = useState(false)
  const [showOff, setShowOff] = useState(false)
  const [form, setForm] = useState<Truck | 'new' | null>(null)
  const [view, setView] = useState<Truck | null>(null)
  const load = () => api<Truck[]>('/setup/vehicles').then((r) => { setRows(r); setView((v) => (v ? r.find((x) => x.id === v.id) ?? null : v)) }).catch(() => setError(true))
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
      <Table head={[t('setup.truck.reg'), t('setup.truck.type'), t('setup.truck.owner'), t('setup.truck.papers'), t('onb.truck.avail'), t('drv.status'), '']} empty={shown.length ? undefined : t('setup.none')}>
        {shown.map((v) => (
          <tr key={v.id} className={`border-t border-line ${v.is_active ? '' : 'text-muted'}`}>
            <td className="px-4 py-3 font-medium tabular-nums">{v.reg_no}</td>
            <td className="px-4 py-3">{[v.vehicle_type, v.capacity_tonnes ? `${v.capacity_tonnes} t` : null].filter(Boolean).join(' · ') || '—'}</td>
            <td className="px-4 py-3">{v.is_hired ? [t('setup.hired'), v.vendor].filter(Boolean).join(' · ') : t('onb.truck.own')}</td>
            <td className={`px-4 py-3 ${v.papers ? PAPER_CLS[v.papers] : 'text-muted'}`}>{v.papers ? t(`setup.truck.${v.papers}`) : '—'}</td>
            <td className={`px-4 py-3 ${AVAIL_CLS[v.availability]}`}>{t(`onb.avail.${v.availability}`)}</td>
            <td className="px-4 py-3"><StatusPill active={v.is_active} /></td>
            <td className="px-4 py-3">
              <div className="flex justify-end gap-2">
                <button onClick={() => setView(v)} className={`${btnGhost} inline-flex items-center gap-1.5`}><Eye size={14} aria-hidden /> {t('onb.details')}</button>
                {canEdit && <button onClick={() => setForm(v)} className={`${btnGhost} inline-flex items-center gap-1.5`}><Pencil size={14} aria-hidden /> {t('setup.edit')}</button>}
              </div>
            </td>
          </tr>
        ))}
      </Table>
      {view && <TruckDetails truck={view} canEdit={canEdit} onClose={() => setView(null)} />}
      {form && <TruckForm truck={form === 'new' ? null : form} vendors={vendors.filter((v) => v.is_active)} onClose={() => setForm(null)} onSaved={() => { setForm(null); void load() }} />}
    </div>
  )
}

function TruckDetails({ truck: v, canEdit, onClose }: { truck: Truck; canEdit: boolean; onClose: () => void }) {
  const { t } = useI18n()
  return (
    <Modal title={v.reg_no} onClose={onClose} wide>
      <Facts rows={[
        [t('setup.truck.type'), v.vehicle_type], [t('setup.truck.capacity'), v.capacity_tonnes ? `${v.capacity_tonnes} t` : null],
        [t('onb.truck.ownership'), v.is_hired ? [t('setup.hired'), v.vendor].filter(Boolean).join(' · ') : t('onb.truck.own')], [t('onb.truck.owner'), v.owner_name],
        [t('onb.truck.avail'), <span className={AVAIL_CLS[v.availability]}>{t(`onb.avail.${v.availability}`)}{v.availability_note ? ` · ${v.availability_note}` : ''}</span>],
        [t('drv.status'), <StatusPill active={v.is_active} />],
      ]} />
      <h3 className="text-sm font-semibold">{t('onb.sec.rc')}</h3>
      <Facts rows={[[t('onb.truck.rcNo'), v.rc_no], [t('onb.truck.regDate'), v.registration_date], [t('onb.truck.chassis'), v.chassis_no], [t('onb.truck.engine'), v.engine_no]]} />
      <h3 className="text-sm font-semibold">{t('onb.sec.papers')}</h3>
      <Facts rows={[
        [t('onb.truck.policy'), v.insurance_no],
        ...EXPIRIES.map(([k, label]): [string, ReactNode] => {
          const st = dayState(v[k])
          return [t(label), v[k] ? <span className={st ? PAPER_CLS[st] : ''}>{v[k]}{st && st !== 'ok' ? ` · ${t(`setup.truck.${st}`)}` : ''}</span> : null]
        }),
      ]} />
      <DocSlots ownerType="vehicle" ownerId={v.id} kinds={VEHICLE_DOCS} canEdit={canEdit} />
      <div className="flex justify-end"><button onClick={onClose} className={btnPrimary}>{t('setup.close')}</button></div>
    </Modal>
  )
}

function TruckForm({ truck, vendors, onClose, onSaved }: { truck: Truck | null; vendors: VendorRef[]; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n()
  const [f, setF] = useState({
    reg_no: truck?.reg_no ?? '', vehicle_type: truck?.vehicle_type ?? '', capacity_tonnes: truck?.capacity_tonnes?.toString() ?? '', owner_name: truck?.owner_name ?? '',
    rc_no: truck?.rc_no ?? '', registration_date: truck?.registration_date ?? '', chassis_no: truck?.chassis_no ?? '', engine_no: truck?.engine_no ?? '',
    insurance_no: truck?.insurance_no ?? '', insurance_expiry: truck?.insurance_expiry ?? '', fitness_expiry: truck?.fitness_expiry ?? '', permit_expiry: truck?.permit_expiry ?? '',
    puc_expiry: truck?.puc_expiry ?? '', vendor_id: truck?.vendor_id ?? '', availability: truck?.availability ?? 'available', availability_note: truck?.availability_note ?? '',
    is_active: truck?.is_active ?? true,
  })
  const [files, setFiles] = useState<Record<string, File | undefined>>({})
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  async function save() {
    const blank = (x: string) => x.trim() || null
    const body = JSON.stringify({
      reg_no: f.reg_no, vehicle_type: blank(f.vehicle_type), capacity_tonnes: blank(f.capacity_tonnes), owner_name: blank(f.owner_name), rc_no: blank(f.rc_no),
      registration_date: blank(f.registration_date), chassis_no: blank(f.chassis_no), engine_no: blank(f.engine_no), insurance_no: blank(f.insurance_no),
      insurance_expiry: blank(f.insurance_expiry), fitness_expiry: blank(f.fitness_expiry), permit_expiry: blank(f.permit_expiry), puc_expiry: blank(f.puc_expiry),
      vendor_id: f.vendor_id || null, availability: f.availability, availability_note: blank(f.availability_note), ...(truck ? { is_active: f.is_active } : {}),
    })
    const saved = await api<Truck>(truck ? `/setup/vehicles/${truck.id}` : '/setup/vehicles', { method: truck ? 'PATCH' : 'POST', body })
    if (!truck) await uploadPending('vehicle', saved.id, files)
    onSaved()
  }
  return (
    <FormModal title={truck ? truck.reg_no : t('setup.truck.add')} onClose={onClose} onSubmit={save} wide>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={t('setup.truck.reg')} hint="MH20 AB 1234"><input className={inputCls} required value={f.reg_no} onChange={set('reg_no')} /></Field>
        <Field label={t('setup.truck.type')}><input className={inputCls} value={f.vehicle_type} onChange={set('vehicle_type')} placeholder="Heavy truck" /></Field>
        <Field label={t('setup.truck.capacity')}><input className={inputCls} inputMode="decimal" value={f.capacity_tonnes} onChange={set('capacity_tonnes')} /></Field>
        <Field label={t('setup.truck.owner')}>
          <select className={inputCls} value={f.vendor_id} onChange={set('vendor_id')}>
            <option value="">{t('onb.truck.own')}</option>
            {vendors.map((v) => <option key={v.id} value={v.id}>{t('setup.hired')} · {v.name}</option>)}
          </select>
        </Field>
        <Field label={t('onb.truck.owner')}><input className={inputCls} value={f.owner_name} onChange={set('owner_name')} /></Field>
        <Field label={t('onb.truck.avail')}>
          <select className={inputCls} value={f.availability} onChange={set('availability')}>
            {(['available', 'maintenance', 'breakdown'] as const).map((a) => <option key={a} value={a}>{t(`onb.avail.${a}`)}</option>)}
          </select>
        </Field>
        {f.availability !== 'available' && <Field label={t('onb.truck.availNote')}><input className={inputCls} maxLength={200} value={f.availability_note} onChange={set('availability_note')} /></Field>}
      </div>
      <h3 className="text-sm font-semibold">{t('onb.sec.rc')}</h3>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={t('onb.truck.rcNo')}><input className={inputCls} value={f.rc_no} onChange={set('rc_no')} /></Field>
        <Field label={t('onb.truck.regDate')}><input type="date" className={inputCls} value={f.registration_date} onChange={set('registration_date')} /></Field>
        <Field label={t('onb.truck.chassis')}><input className={inputCls} value={f.chassis_no} onChange={set('chassis_no')} /></Field>
        <Field label={t('onb.truck.engine')}><input className={inputCls} value={f.engine_no} onChange={set('engine_no')} /></Field>
      </div>
      <h3 className="text-sm font-semibold">{t('onb.sec.papers')}</h3>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={t('onb.truck.policy')}><input className={inputCls} value={f.insurance_no} onChange={set('insurance_no')} /></Field>
        <Field label={t('setup.truck.insurance')}><input type="date" className={inputCls} value={f.insurance_expiry} onChange={set('insurance_expiry')} /></Field>
        <Field label={t('setup.truck.fitness')}><input type="date" className={inputCls} value={f.fitness_expiry} onChange={set('fitness_expiry')} /></Field>
        <Field label={t('setup.truck.permit')}><input type="date" className={inputCls} value={f.permit_expiry} onChange={set('permit_expiry')} /></Field>
        <Field label={t('onb.truck.puc')}><input type="date" className={inputCls} value={f.puc_expiry} onChange={set('puc_expiry')} /></Field>
      </div>
      {truck ? <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> {t('setup.active')}</label>
        : <PendingDocs kinds={VEHICLE_DOCS} files={files} onChange={setFiles} />}
    </FormModal>
  )
}
