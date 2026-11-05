import { Pencil, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import { btnGhost, btnPrimary, Field, FormModal, inputCls, StatusPill, Table } from './ui'

interface ClientRow {
  id: string; name: string; segment: string | null; billing_cycle: 'weekly' | 'fortnightly' | 'monthly' | 'per_trip'; tally_ledger: string | null
  contact_name: string | null; contact_phone: string | null; gstin: string | null; is_active: boolean; trips: number
}

export default function ClientsTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useI18n()
  const [rows, setRows] = useState<ClientRow[] | null>(null)
  const [error, setError] = useState(false)
  const [showOff, setShowOff] = useState(false)
  const [form, setForm] = useState<ClientRow | 'new' | null>(null)
  const load = () => api<ClientRow[]>('/setup/clients').then(setRows).catch(() => setError(true))
  useEffect(() => { void load() }, [])
  if (error) return <p className="text-bad">{t('setup.loadFail')}</p>
  if (!rows) return <p className="text-muted">{t('common.loading')}</p>
  const shown = rows.filter((c) => showOff || c.is_active)
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={showOff} onChange={(e) => setShowOff(e.target.checked)} /> {t('setup.showInactive')}</label>
        {canEdit && <button onClick={() => setForm('new')} className={`${btnPrimary} inline-flex items-center gap-1.5`}><Plus size={16} aria-hidden /> {t('setup.client.add')}</button>}
      </div>
      <Table head={[t('setup.client.name'), t('setup.client.cycle'), t('setup.client.ledger'), t('setup.client.contact'), t('setup.client.trips'), t('drv.status'), '']} empty={shown.length ? undefined : t('setup.none')}>
        {shown.map((c) => (
          <tr key={c.id} className={`border-t border-line ${c.is_active ? '' : 'text-muted'}`}>
            <td className="px-4 py-3 font-medium">{c.name}{c.segment && <span className="block text-xs font-normal text-muted">{c.segment}</span>}</td>
            <td className="px-4 py-3">{t(`setup.cycle.${c.billing_cycle}`)}</td>
            <td className="px-4 py-3">{c.tally_ledger ?? <span className="text-muted">—</span>}</td>
            <td className="px-4 py-3">{c.contact_name ?? '—'}{c.contact_phone && <span className="block text-xs tabular-nums text-muted">{c.contact_phone}</span>}</td>
            <td className="px-4 py-3 tabular-nums">{c.trips}</td>
            <td className="px-4 py-3"><StatusPill active={c.is_active} /></td>
            <td className="px-4 py-3 text-right">{canEdit && <button onClick={() => setForm(c)} className={`${btnGhost} inline-flex items-center gap-1.5`}><Pencil size={14} aria-hidden /> {t('setup.edit')}</button>}</td>
          </tr>
        ))}
      </Table>
      {form && <ClientForm client={form === 'new' ? null : form} onClose={() => setForm(null)} onSaved={() => { setForm(null); void load() }} />}
    </div>
  )
}

function ClientForm({ client, onClose, onSaved }: { client: ClientRow | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n()
  const [f, setF] = useState({
    name: client?.name ?? '', segment: client?.segment ?? '', billing_cycle: client?.billing_cycle ?? 'weekly', tally_ledger: client?.tally_ledger ?? '',
    contact_name: client?.contact_name ?? '', contact_phone: client?.contact_phone ?? '', gstin: client?.gstin ?? '', is_active: client?.is_active ?? true,
  })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  async function save() {
    const body = JSON.stringify({ ...f, segment: f.segment || null, tally_ledger: f.tally_ledger || null, contact_name: f.contact_name || null, contact_phone: f.contact_phone || null, gstin: f.gstin || null, ...(client ? {} : { is_active: undefined }) })
    await api(client ? `/setup/clients/${client.id}` : '/setup/clients', { method: client ? 'PATCH' : 'POST', body })
    onSaved()
  }
  return (
    <FormModal title={client ? client.name : t('setup.client.add')} onClose={onClose} onSubmit={save}>
      <Field label={t('setup.client.name')}><input className={inputCls} required minLength={2} value={f.name} onChange={set('name')} /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label={t('setup.client.segment')}><input className={inputCls} value={f.segment} onChange={set('segment')} /></Field>
        <Field label={t('setup.client.cycle')}>
          <select className={inputCls} value={f.billing_cycle} onChange={set('billing_cycle')}>
            {(['weekly', 'fortnightly', 'monthly', 'per_trip'] as const).map((c) => <option key={c} value={c}>{t(`setup.cycle.${c}`)}</option>)}
          </select>
        </Field>
      </div>
      <Field label={t('setup.client.ledger')}><input className={inputCls} value={f.tally_ledger} onChange={set('tally_ledger')} /></Field>
      <Field label={t('setup.client.gstin')} hint="27ABCDE1234F1Z5"><input className={inputCls} maxLength={15} value={f.gstin} onChange={(e) => setF({ ...f, gstin: e.target.value.toUpperCase() })} /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label={t('setup.client.contact')}><input className={inputCls} value={f.contact_name} onChange={set('contact_name')} /></Field>
        <Field label={t('setup.client.phone')}><input className={inputCls} inputMode="tel" value={f.contact_phone} onChange={set('contact_phone')} /></Field>
      </div>
      {client && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> {t('setup.active')}</label>}
    </FormModal>
  )
}
