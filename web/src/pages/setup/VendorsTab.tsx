import { Pencil, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import { btnGhost, btnPrimary, Field, FormModal, inputCls, StatusPill, Table } from './ui'

interface Vendor { id: string; name: string; contact_name: string | null; phone: string | null; notes: string | null; is_active: boolean; trucks: number; drivers: number }

export default function VendorsTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useI18n()
  const [rows, setRows] = useState<Vendor[] | null>(null)
  const [error, setError] = useState(false)
  const [form, setForm] = useState<Vendor | 'new' | null>(null)
  const load = () => api<Vendor[]>('/setup/vendors').then(setRows).catch(() => setError(true))
  useEffect(() => { void load() }, [])
  if (error) return <p className="text-bad">{t('setup.loadFail')}</p>
  if (!rows) return <p className="text-muted">{t('common.loading')}</p>
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-xl text-sm text-muted">{t('setup.vendor.help')}</p>
        {canEdit && <button onClick={() => setForm('new')} className={`${btnPrimary} inline-flex items-center gap-1.5`}><Plus size={16} aria-hidden /> {t('setup.vendor.add')}</button>}
      </div>
      <Table head={[t('setup.vendor.name'), t('setup.vendor.contact'), t('setup.vendor.trucks'), t('setup.vendor.drivers'), t('drv.status'), '']} empty={rows.length ? undefined : t('setup.none')}>
        {rows.map((v) => (
          <tr key={v.id} className={`border-t border-line ${v.is_active ? '' : 'text-muted'}`}>
            <td className="px-4 py-3 font-medium">{v.name}{v.notes && <span className="block text-xs font-normal text-muted">{v.notes}</span>}</td>
            <td className="px-4 py-3">{v.contact_name ?? '—'}{v.phone && <span className="block text-xs tabular-nums text-muted">{v.phone}</span>}</td>
            <td className="px-4 py-3 tabular-nums">{v.trucks}</td>
            <td className="px-4 py-3 tabular-nums">{v.drivers}</td>
            <td className="px-4 py-3"><StatusPill active={v.is_active} /></td>
            <td className="px-4 py-3 text-right">{canEdit && <button onClick={() => setForm(v)} className={`${btnGhost} inline-flex items-center gap-1.5`}><Pencil size={14} aria-hidden /> {t('setup.edit')}</button>}</td>
          </tr>
        ))}
      </Table>
      {form && <VendorForm vendor={form === 'new' ? null : form} onClose={() => setForm(null)} onSaved={() => { setForm(null); void load() }} />}
    </div>
  )
}

function VendorForm({ vendor, onClose, onSaved }: { vendor: Vendor | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n()
  const [f, setF] = useState({ name: vendor?.name ?? '', contact_name: vendor?.contact_name ?? '', phone: vendor?.phone ?? '', notes: vendor?.notes ?? '', is_active: vendor?.is_active ?? true })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  async function save() {
    const body = JSON.stringify({ name: f.name, contact_name: f.contact_name || null, phone: f.phone || null, notes: f.notes || null, ...(vendor ? { is_active: f.is_active } : {}) })
    await api(vendor ? `/setup/vendors/${vendor.id}` : '/setup/vendors', { method: vendor ? 'PATCH' : 'POST', body })
    onSaved()
  }
  return (
    <FormModal title={vendor ? vendor.name : t('setup.vendor.add')} onClose={onClose} onSubmit={save}>
      <Field label={t('setup.vendor.name')}><input className={inputCls} required minLength={2} value={f.name} onChange={set('name')} /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label={t('setup.vendor.contact')}><input className={inputCls} value={f.contact_name} onChange={set('contact_name')} /></Field>
        <Field label={t('setup.vendor.phone')}><input className={inputCls} inputMode="tel" value={f.phone} onChange={set('phone')} /></Field>
      </div>
      <Field label={t('setup.vendor.notes')}><input className={inputCls} maxLength={300} value={f.notes} onChange={set('notes')} /></Field>
      {vendor && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> {t('setup.active')}</label>}
    </FormModal>
  )
}
