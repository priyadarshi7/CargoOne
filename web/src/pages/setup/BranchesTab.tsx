import { Pencil, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import { btnGhost, btnPrimary, Field, FormModal, inputCls, Table } from './ui'

interface Branch { id: string; name: string; code: string | null; trips: number }

/** Branches and the code that starts every LR number issued from them. */
export default function BranchesTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useI18n()
  const [rows, setRows] = useState<Branch[] | null>(null)
  const [error, setError] = useState(false)
  const [form, setForm] = useState<Branch | 'new' | null>(null)
  const load = () => api<Branch[]>('/setup/branches').then(setRows).catch(() => setError(true))
  useEffect(() => { void load() }, [])
  if (error) return <p className="text-bad">{t('setup.loadFail')}</p>
  if (!rows) return <p className="text-muted">{t('common.loading')}</p>
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        {canEdit && <button onClick={() => setForm('new')} className={`${btnPrimary} inline-flex items-center gap-1.5`}><Plus size={16} aria-hidden /> {t('setup.branch.add')}</button>}
      </div>
      <Table head={[t('setup.branch.name'), t('setup.branch.code'), t('setup.branch.trips'), '']} empty={rows.length ? undefined : t('setup.none')}>
        {rows.map((b) => (
          <tr key={b.id} className="border-t border-line">
            <td className="px-4 py-3 font-medium">{b.name}</td>
            <td className="px-4 py-3 tabular-nums">{b.code ?? '—'}</td>
            <td className="px-4 py-3 tabular-nums">{b.trips}</td>
            <td className="px-4 py-3 text-right">{canEdit && <button onClick={() => setForm(b)} className={`${btnGhost} inline-flex items-center gap-1.5`}><Pencil size={14} aria-hidden /> {t('setup.edit')}</button>}</td>
          </tr>
        ))}
      </Table>
      {form && <BranchForm branch={form === 'new' ? null : form} onClose={() => setForm(null)} onSaved={() => { setForm(null); void load() }} />}
    </div>
  )
}

function BranchForm({ branch, onClose, onSaved }: { branch: Branch | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n()
  const [f, setF] = useState({ name: branch?.name ?? '', code: branch?.code ?? '' })
  async function save() {
    await api(branch ? `/setup/branches/${branch.id}` : '/setup/branches', { method: branch ? 'PATCH' : 'POST', body: JSON.stringify(f) })
    onSaved()
  }
  return (
    <FormModal title={branch ? branch.name : t('setup.branch.add')} onClose={onClose} onSubmit={save}>
      <Field label={t('setup.branch.name')}><input className={inputCls} required minLength={2} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
      <Field label={t('setup.branch.code')} hint={t('setup.branch.codeHint')}>
        <input className={inputCls} required pattern="[A-Za-z0-9]{2,8}" maxLength={8} value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} />
      </Field>
    </FormModal>
  )
}
