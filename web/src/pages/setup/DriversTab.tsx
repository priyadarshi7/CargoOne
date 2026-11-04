import { KeyRound, Lock, Pencil, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, ApiError } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import { btnGhost, btnPrimary, Field, FormModal, inputCls, Modal, Secret, StatusPill, Table } from './ui'

export interface Driver {
  id: string; name: string; phone: string | null; language: string; branch: string | null; vendor_id: string | null; vendor: string | null
  is_active: boolean; locked: boolean; must_change_pin: boolean
}
export interface VendorRef { id: string; name: string; is_active: boolean }

export default function DriversTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useI18n()
  const [rows, setRows] = useState<Driver[] | null>(null)
  const [vendors, setVendors] = useState<VendorRef[]>([])
  const [error, setError] = useState(false)
  const [showOff, setShowOff] = useState(false)
  const [form, setForm] = useState<Driver | 'new' | null>(null)
  const [reset, setReset] = useState<Driver | null>(null)
  const [secret, setSecret] = useState<{ title: string; note: string; value: string } | null>(null)

  const load = () => api<Driver[]>('/drivers').then(setRows).catch(() => setError(true))
  useEffect(() => { void load(); api<VendorRef[]>('/setup/vendors').then(setVendors).catch(() => undefined) }, [])
  if (error) return <p className="text-bad">{t('setup.loadFail')}</p>
  if (!rows) return <p className="text-muted">{t('common.loading')}</p>
  const shown = rows.filter((d) => showOff || d.is_active)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={showOff} onChange={(e) => setShowOff(e.target.checked)} /> {t('setup.showInactive')}</label>
        {canEdit && <button onClick={() => setForm('new')} className={`${btnPrimary} inline-flex items-center gap-1.5`}><Plus size={16} aria-hidden /> {t('setup.drv.add')}</button>}
      </div>
      <Table head={[t('drv.name'), t('drv.phone'), t('setup.drv.hiredFrom'), t('drv.status'), '']} empty={shown.length ? undefined : t('setup.none')}>
        {shown.map((d) => (
          <tr key={d.id} className={`border-t border-line ${d.is_active ? '' : 'text-muted'}`}>
            <td className="px-4 py-3 font-medium">{d.name}</td>
            <td className="px-4 py-3 tabular-nums">{d.phone ?? '—'}</td>
            <td className="px-4 py-3">{d.vendor ?? t('setup.drv.ownStaff')}</td>
            <td className="px-4 py-3">
              {!d.is_active ? <StatusPill active={false} />
                : d.locked ? <span className="inline-flex items-center gap-1 text-bad"><Lock size={14} aria-hidden /> {t('drv.locked')}</span>
                : d.must_change_pin ? <span className="text-warn">{t('drv.temp')}</span> : <span className="text-muted">{t('drv.ok')}</span>}
            </td>
            <td className="px-4 py-3">
              <div className="flex justify-end gap-2">
                {canEdit && <button onClick={() => setForm(d)} className={`${btnGhost} inline-flex items-center gap-1.5`}><Pencil size={14} aria-hidden /> {t('setup.edit')}</button>}
                {d.is_active && <button onClick={() => setReset(d)} className={`${btnGhost} inline-flex items-center gap-1.5`}><KeyRound size={14} aria-hidden /> {t('drv.reset')}</button>}
              </div>
            </td>
          </tr>
        ))}
      </Table>

      {form && <DriverForm driver={form === 'new' ? null : form} vendors={vendors.filter((v) => v.is_active)} onClose={() => setForm(null)}
        onSaved={(pin, d) => { setForm(null); void load(); if (pin) setSecret({ title: t('setup.drv.pinTitle', { name: d.name }), note: t('setup.drv.pinNote', { name: d.name }), value: pin }) }} />}
      {reset && <ResetDialog driver={reset} onClose={() => setReset(null)} onPin={(pin) => { setSecret({ title: t('drv.tempFor', { name: reset.name }), note: t('drv.tempNote'), value: pin }); setReset(null); void load() }} />}
      {secret && <Secret {...secret} onClose={() => setSecret(null)} />}
    </div>
  )
}

function DriverForm({ driver, vendors, onClose, onSaved }: { driver: Driver | null; vendors: VendorRef[]; onClose: () => void; onSaved: (pin: string | null, d: Driver) => void }) {
  const { t } = useI18n()
  const [f, setF] = useState({ name: driver?.name ?? '', phone: driver?.phone ?? '', language: driver?.language ?? 'hi', vendor_id: driver?.vendor_id ?? '' })
  const [confirmOff, setConfirmOff] = useState(false)
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })

  async function save() {
    if (!driver) {
      const res = await api<{ driver: Driver; pin: string }>('/drivers', { method: 'POST', body: JSON.stringify({ ...f, vendor_id: f.vendor_id || null }) })
      return onSaved(res.pin, res.driver)
    }
    const d = await api<Driver>(`/drivers/${driver.id}`, { method: 'PATCH', body: JSON.stringify({ name: f.name, phone: f.phone, language: f.language, vendor_id: f.vendor_id || null, clear_vendor: !f.vendor_id }) })
    onSaved(null, d)
  }

  if (confirmOff && driver) return <ToggleDialog driver={driver} onClose={() => setConfirmOff(false)} onDone={(d) => onSaved(null, d)} />
  return (
    <FormModal title={driver ? driver.name : t('setup.drv.add')} onClose={onClose} onSubmit={save}>
      <Field label={t('drv.name')}><input className={inputCls} required minLength={2} value={f.name} onChange={set('name')} /></Field>
      <Field label={t('drv.phone')} hint={t('setup.drv.phoneHint')}><input className={inputCls} required inputMode="tel" value={f.phone} onChange={set('phone')} /></Field>
      <Field label={t('setup.drv.language')}>
        <select className={inputCls} value={f.language} onChange={set('language')}><option value="hi">हिन्दी</option><option value="mr">मराठी</option><option value="en">English</option></select>
      </Field>
      <Field label={t('setup.drv.hiredFrom')}>
        <select className={inputCls} value={f.vendor_id} onChange={set('vendor_id')}>
          <option value="">{t('setup.drv.ownStaff')}</option>
          {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
        </select>
      </Field>
      {driver && <button type="button" onClick={() => setConfirmOff(true)} className="text-sm text-bad underline">{driver.is_active ? t('setup.deactivate') : t('setup.reactivate')}</button>}
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
