import { Eye, KeyRound, Lock, MessageCircle, Pencil, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, ApiError } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import { DocSlots, DRIVER_DOCS, PendingDocs, uploadPending } from './Docs'
import InviteDialog, { type Invite } from './Invite'
import type { Truck } from './TrucksTab'
import { btnGhost, btnPrimary, Facts, Field, FormModal, inputCls, Modal, Secret, StatusPill, Table } from './ui'

export interface Driver {
  id: string; name: string; phone: string | null; language: string; branch: string | null; vendor_id: string | null; vendor: string | null
  is_active: boolean; locked: boolean; must_change_pin: boolean; employment_type: 'company' | 'contract' | 'hired' | null
  licence_no: string | null; licence_expiry: string | null; licence: 'ok' | 'due_soon' | 'expired' | null; assigned_vehicle_id: string | null; assigned_vehicle: string | null
}
const LIC_CLS = { ok: 'text-ok', due_soon: 'text-warn', expired: 'text-bad' } as const
export interface VendorRef { id: string; name: string; is_active: boolean }

export default function DriversTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useI18n()
  const [rows, setRows] = useState<Driver[] | null>(null)
  const [vendors, setVendors] = useState<VendorRef[]>([])
  const [trucks, setTrucks] = useState<Truck[]>([])
  const [view, setView] = useState<Driver | null>(null)
  const [error, setError] = useState(false)
  const [showOff, setShowOff] = useState(false)
  const [form, setForm] = useState<Driver | 'new' | null>(null)
  const [reset, setReset] = useState<Driver | null>(null)
  const [secret, setSecret] = useState<{ title: string; note: string; value: string } | null>(null)
  const [invite, setInvite] = useState<{ name: string; pin: string | null; invite: Invite } | null>(null)
  const [sendError, setSendError] = useState<string | null>(null)

  async function resend(d: Driver) {
    setSendError(null)
    try { setInvite({ name: d.name, pin: null, invite: await api<Invite>(`/drivers/${d.id}/invite`, { method: 'POST' }) }) }
    catch (e) { setSendError(e instanceof ApiError ? e.message : t('notif.sendFail')) }
  }

  const load = () => api<Driver[]>('/drivers').then((r) => { setRows(r); setView((v) => (v ? r.find((x) => x.id === v.id) ?? null : v)) }).catch(() => setError(true))
  useEffect(() => {
    void load()
    api<VendorRef[]>('/setup/vendors').then(setVendors).catch(() => undefined)
    api<Truck[]>('/setup/vehicles').then(setTrucks).catch(() => undefined)
  }, [])
  if (error) return <p className="text-bad">{t('setup.loadFail')}</p>
  if (!rows) return <p className="text-muted">{t('common.loading')}</p>
  const shown = rows.filter((d) => showOff || d.is_active)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={showOff} onChange={(e) => setShowOff(e.target.checked)} /> {t('setup.showInactive')}</label>
        {canEdit && <button onClick={() => setForm('new')} className={`${btnPrimary} inline-flex items-center gap-1.5`}><Plus size={16} aria-hidden /> {t('setup.drv.add')}</button>}
      </div>
      <Table head={[t('drv.name'), t('drv.phone'), t('onb.drv.employment'), t('onb.drv.vehicle'), t('onb.drv.licence'), t('drv.status'), '']} empty={shown.length ? undefined : t('setup.none')}>
        {shown.map((d) => (
          <tr key={d.id} className={`border-t border-line ${d.is_active ? '' : 'text-muted'}`}>
            <td className="px-4 py-3 font-medium">{d.name}</td>
            <td className="px-4 py-3 tabular-nums">{d.phone ?? '—'}</td>
            <td className="px-4 py-3">{d.employment_type ? [t(`onb.emp.${d.employment_type}`), d.vendor].filter(Boolean).join(' · ') : '—'}</td>
            <td className="px-4 py-3 tabular-nums">{d.assigned_vehicle ?? '—'}</td>
            <td className={`px-4 py-3 ${d.licence ? LIC_CLS[d.licence] : 'text-muted'}`}>{d.licence ? t(`setup.truck.${d.licence}`) : '—'}</td>
            <td className="px-4 py-3">
              {!d.is_active ? <StatusPill active={false} />
                : d.locked ? <span className="inline-flex items-center gap-1 text-bad"><Lock size={14} aria-hidden /> {t('drv.locked')}</span>
                : d.must_change_pin ? <span className="text-warn">{t('drv.temp')}</span> : <span className="text-muted">{t('drv.ok')}</span>}
            </td>
            <td className="px-4 py-3">
              <div className="flex justify-end gap-2">
                <button onClick={() => setView(d)} className={`${btnGhost} inline-flex items-center gap-1.5`}><Eye size={14} aria-hidden /> {t('onb.details')}</button>
                {canEdit && <button onClick={() => setForm(d)} className={`${btnGhost} inline-flex items-center gap-1.5`}><Pencil size={14} aria-hidden /> {t('setup.edit')}</button>}
                {canEdit && d.is_active && d.must_change_pin && <button onClick={() => void resend(d)} className={`${btnGhost} inline-flex items-center gap-1.5`}><MessageCircle size={14} aria-hidden /> {t('notif.sendLink')}</button>}
                {d.is_active && <button onClick={() => setReset(d)} className={`${btnGhost} inline-flex items-center gap-1.5`}><KeyRound size={14} aria-hidden /> {t('drv.reset')}</button>}
              </div>
            </td>
          </tr>
        ))}
      </Table>

      {view && <DriverDetails driver={view} canEdit={canEdit} onClose={() => setView(null)} />}
      {form && <DriverForm driver={form === 'new' ? null : form} vendors={vendors.filter((v) => v.is_active)} trucks={trucks.filter((x) => x.is_active)} onClose={() => setForm(null)}
        onSaved={(pin, d, inv) => { setForm(null); void load(); if (pin && inv) setInvite({ name: d.name, pin, invite: inv }); else if (pin) setSecret({ title: t('setup.drv.pinTitle', { name: d.name }), note: t('setup.drv.pinNote', { name: d.name }), value: pin }) }} />}
      {invite && <InviteDialog name={invite.name} pin={invite.pin} invite={invite.invite} onClose={() => setInvite(null)} />}
      {sendError && <p role="alert" className="text-sm text-bad">{sendError}</p>}
      {reset && <ResetDialog driver={reset} onClose={() => setReset(null)} onPin={(pin) => { setSecret({ title: t('drv.tempFor', { name: reset.name }), note: t('drv.tempNote'), value: pin }); setReset(null); void load() }} />}
      {secret && <Secret {...secret} onClose={() => setSecret(null)} />}
    </div>
  )
}

function DriverDetails({ driver: d, canEdit, onClose }: { driver: Driver; canEdit: boolean; onClose: () => void }) {
  const { t } = useI18n()
  return (
    <Modal title={d.name} onClose={onClose} wide>
      <Facts rows={[
        [t('drv.phone'), d.phone], [t('setup.drv.language'), { hi: 'हिन्दी', mr: 'मराठी', en: 'English' }[d.language]],
        [t('onb.drv.employment'), d.employment_type ? [t(`onb.emp.${d.employment_type}`), d.vendor].filter(Boolean).join(' · ') : null],
        [t('onb.drv.vehicle'), d.assigned_vehicle], [t('onb.drv.licenceNo'), d.licence_no],
        [t('onb.drv.licenceExpiry'), d.licence_expiry ? <span className={d.licence ? LIC_CLS[d.licence] : ''}>{d.licence_expiry}{d.licence && d.licence !== 'ok' ? ` · ${t(`setup.truck.${d.licence}`)}` : ''}</span> : null],
        [t('drv.status'), <StatusPill active={d.is_active} />],
      ]} />
      {canEdit && <DocSlots ownerType="driver" ownerId={d.id} kinds={DRIVER_DOCS} canEdit />}
      <div className="flex justify-end"><button onClick={onClose} className={btnPrimary}>{t('setup.close')}</button></div>
    </Modal>
  )
}

function DriverForm({ driver, vendors, trucks, onClose, onSaved }: { driver: Driver | null; vendors: VendorRef[]; trucks: Truck[]; onClose: () => void; onSaved: (pin: string | null, d: Driver, inv?: Invite | null) => void }) {
  const { t } = useI18n()
  const [f, setF] = useState({
    name: driver?.name ?? '', phone: driver?.phone ?? '', language: driver?.language ?? 'hi', employment_type: driver?.employment_type ?? 'company', vendor_id: driver?.vendor_id ?? '',
    licence_no: driver?.licence_no ?? '', licence_expiry: driver?.licence_expiry ?? '', assigned_vehicle_id: driver?.assigned_vehicle_id ?? '',
  })
  const [files, setFiles] = useState<Record<string, File | undefined>>({})
  const [confirmOff, setConfirmOff] = useState(false)
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const hired = f.employment_type === 'hired'

  async function save() {
    const common = { name: f.name, phone: f.phone, language: f.language, employment_type: f.employment_type, vendor_id: hired ? f.vendor_id || null : null, licence_no: f.licence_no, licence_expiry: f.licence_expiry }
    if (!driver) {
      const res = await api<{ driver: Driver; pin: string; invite: Invite | null }>('/drivers', { method: 'POST', body: JSON.stringify({ ...common, assigned_vehicle_id: f.assigned_vehicle_id || null }) })
      await uploadPending('driver', res.driver.id, files)
      return onSaved(res.pin, res.driver, res.invite)
    }
    const d = await api<Driver>(`/drivers/${driver.id}`, { method: 'PATCH', body: JSON.stringify({ ...common, clear_vendor: !hired, assigned_vehicle_id: f.assigned_vehicle_id || null, clear_vehicle: !f.assigned_vehicle_id }) })
    onSaved(null, d)
  }

  if (confirmOff && driver) return <ToggleDialog driver={driver} onClose={() => setConfirmOff(false)} onDone={(d) => onSaved(null, d)} />
  return (
    <FormModal title={driver ? driver.name : t('setup.drv.add')} onClose={onClose} onSubmit={save} wide>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={t('drv.name')}><input className={inputCls} required minLength={2} value={f.name} onChange={set('name')} /></Field>
        <Field label={t('drv.phone')} hint={t('setup.drv.phoneHint')}><input className={inputCls} required inputMode="tel" value={f.phone} onChange={set('phone')} /></Field>
        <Field label={t('onb.drv.licenceNo')}><input className={inputCls} required value={f.licence_no} onChange={set('licence_no')} /></Field>
        <Field label={t('onb.drv.licenceExpiry')}><input type="date" className={inputCls} required value={f.licence_expiry} onChange={set('licence_expiry')} /></Field>
        <Field label={t('onb.drv.employment')}>
          <select className={inputCls} value={f.employment_type} onChange={set('employment_type')}>
            {(['company', 'contract', 'hired'] as const).map((e) => <option key={e} value={e}>{t(`onb.emp.${e}`)}</option>)}
          </select>
        </Field>
        {hired && (
          <Field label={t('setup.drv.hiredFrom')}>
            <select className={inputCls} required value={f.vendor_id} onChange={set('vendor_id')}>
              <option value="" />
              {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </Field>
        )}
        <Field label={t('onb.drv.vehicle')}>
          <select className={inputCls} value={f.assigned_vehicle_id} onChange={set('assigned_vehicle_id')}>
            <option value="">{t('onb.drv.noVehicle')}</option>
            {trucks.map((v) => <option key={v.id} value={v.id}>{v.reg_no}</option>)}
          </select>
        </Field>
        <Field label={t('setup.drv.language')}>
          <select className={inputCls} value={f.language} onChange={set('language')}><option value="hi">हिन्दी</option><option value="mr">मराठी</option><option value="en">English</option></select>
        </Field>
      </div>
      {driver ? <button type="button" onClick={() => setConfirmOff(true)} className="text-sm text-bad underline">{driver.is_active ? t('setup.deactivate') : t('setup.reactivate')}</button>
        : <PendingDocs kinds={DRIVER_DOCS} files={files} onChange={setFiles} />}
    </FormModal>
  )
}

function ToggleDialog({ driver, onClose, onDone }: { driver: Driver; onClose: () => void; onDone: (d: Driver) => void }) {
  const { t } = useI18n()
  const [error, setError] = useState<string | null>(null)
  async function go() {
    try { onDone(await api<Driver>(`/drivers/${driver.id}`, { method: 'PATCH', body: JSON.stringify({ is_active: !driver.is_active }) })) }
    catch (e) { setError(e instanceof ApiError ? e.message : t('setup.saveFail')) }
  }
  return (
    <Modal title={driver.name} onClose={onClose}>
      <p className="text-sm text-muted">{driver.is_active ? t('setup.drv.deactivateAsk', { name: driver.name }) : driver.name}</p>
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      <div className="flex justify-end gap-3">
        <button onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-sm">{t('setup.cancel')}</button>
        <button onClick={() => void go()} className={btnPrimary}>{driver.is_active ? t('setup.deactivate') : t('setup.reactivate')}</button>
      </div>
    </Modal>
  )
}

function ResetDialog({ driver, onClose, onPin }: { driver: Driver; onClose: () => void; onPin: (pin: string) => void }) {
  const { t } = useI18n()
  const [error, setError] = useState<string | null>(null)
  async function go() {
    try { onPin((await api<{ pin: string }>(`/drivers/${driver.id}/reset-pin`, { method: 'POST' })).pin) }
    catch (e) { setError(e instanceof ApiError ? e.message : t('drv.resetFail')) }
  }
  return (
    <Modal title={t('drv.confirmTitle', { name: driver.name })} onClose={onClose}>
      <p className="text-sm text-muted">{t('drv.confirmBody', { name: driver.name })}</p>
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      <div className="flex justify-end gap-3">
        <button onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-sm">{t('setup.cancel')}</button>
        <button onClick={() => void go()} className={btnPrimary}>{t('drv.reset')}</button>
      </div>
    </Modal>
  )
}
