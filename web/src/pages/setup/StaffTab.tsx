import { KeyRound, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { useBusy } from '../../lib/busy'
import { useI18n } from '../../lib/i18n'
import { btnGhost, btnPrimary, Field, FormModal, inputCls, Secret, Spin, StatusPill, Table } from './ui'

interface Staff { id: string; name: string; email: string; role: 'ops' | 'billing' | 'md' | 'admin'; language: string; is_active: boolean; must_change_password: boolean }

export default function StaffTab() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [rows, setRows] = useState<Staff[] | null>(null)
  const [error, setError] = useState(false)
  const [adding, setAdding] = useState(false)
  const [secret, setSecret] = useState<{ title: string; note: string; value: string } | null>(null)
  const { busy, run } = useBusy()
  const load = () => api<Staff[]>('/setup/staff').then(setRows).catch(() => setError(true))
  useEffect(() => { void load() }, [])
  if (error) return <p className="text-bad">{t('setup.loadFail')}</p>
  if (!rows) return <p className="text-muted">{t('common.loading')}</p>

  async function toggle(s: Staff) { await api(`/setup/staff/${s.id}`, { method: 'PATCH', body: JSON.stringify({ is_active: !s.is_active }) }); void load() }
  async function reset(s: Staff) {
    const r = await api<{ password: string }>(`/setup/staff/${s.id}/reset-password`, { method: 'POST' })
    setSecret({ title: t('setup.staff.pwTitle', { name: s.name }), note: t('setup.staff.pwNote', { name: s.name }), value: r.password })
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end"><button onClick={() => setAdding(true)} className={`${btnPrimary} inline-flex items-center gap-1.5`}><Plus size={16} aria-hidden /> {t('setup.staff.add')}</button></div>
      <Table head={[t('setup.staff.name'), t('setup.staff.email'), t('setup.staff.role'), t('drv.status'), '']}>
        {rows.map((s) => (
          <tr key={s.id} className={`border-t border-line ${s.is_active ? '' : 'text-muted'}`}>
            <td className="px-4 py-3 font-medium">{s.name}</td>
            <td className="px-4 py-3">{s.email}</td>
            <td className="px-4 py-3">{t(`setup.role.${s.role}`)}</td>
            <td className="px-4 py-3"><StatusPill active={s.is_active} /></td>
            <td className="px-4 py-3">
              {s.role !== 'admin' && s.id !== user?.id && (
                <div className="flex justify-end gap-2">
                  <button disabled={!!busy} onClick={() => void run(`reset-${s.id}`, () => reset(s))} className={`${btnGhost} inline-flex items-center gap-1.5 disabled:opacity-60`}>{busy === `reset-${s.id}` ? <Spin /> : <KeyRound size={14} aria-hidden />} {t('setup.staff.resetPw')}</button>
                  <button disabled={!!busy} onClick={() => void run(`toggle-${s.id}`, () => toggle(s))} className={`${btnGhost} disabled:opacity-60`}>{busy === `toggle-${s.id}` && <Spin />}{s.is_active ? t('setup.deactivate') : t('setup.reactivate')}</button>
                </div>
              )}
            </td>
          </tr>
        ))}
      </Table>
      {adding && <StaffForm onClose={() => setAdding(false)} onSaved={(s, pw) => { setAdding(false); void load(); setSecret({ title: t('setup.staff.pwTitle', { name: s.name }), note: t('setup.staff.pwNote', { name: s.name }), value: pw }) }} />}
      {secret && <Secret {...secret} onClose={() => setSecret(null)} />}
    </div>
  )
}

function StaffForm({ onClose, onSaved }: { onClose: () => void; onSaved: (s: Staff, pw: string) => void }) {
  const { t } = useI18n()
  const [f, setF] = useState({ name: '', email: '', role: 'billing', language: 'en' })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  async function save() { const r = await api<{ staff: Staff; password: string }>('/setup/staff', { method: 'POST', body: JSON.stringify(f) }); onSaved(r.staff, r.password) }
  return (
    <FormModal title={t('setup.staff.add')} onClose={onClose} onSubmit={save}>
      <Field label={t('setup.staff.name')}><input className={inputCls} required minLength={2} value={f.name} onChange={set('name')} /></Field>
      <Field label={t('setup.staff.email')}><input type="email" className={inputCls} required value={f.email} onChange={set('email')} /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label={t('setup.staff.role')}>
          <select className={inputCls} value={f.role} onChange={set('role')}>{(['ops', 'billing', 'md'] as const).map((r) => <option key={r} value={r}>{t(`setup.role.${r}`)}</option>)}</select>
        </Field>
        <Field label={t('setup.drv.language')}>
          <select className={inputCls} value={f.language} onChange={set('language')}><option value="en">English</option><option value="hi">हिन्दी</option><option value="mr">मराठी</option></select>
        </Field>
      </div>
    </FormModal>
  )
}
