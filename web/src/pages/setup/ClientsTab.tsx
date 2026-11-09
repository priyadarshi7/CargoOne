import { KeyRound, Pencil, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { FilterBar, NoMatch, type FilterSelect } from '../../components/FilterBar'
import { hit, useFilters } from '../../lib/filters'
import { useBusy } from '../../lib/busy'
import { useI18n } from '../../lib/i18n'
import { api, ApiError } from '../../lib/api'
import { btnGhost, btnPrimary, Field, FormModal, inputCls, Modal, Spin, StatusPill, Table } from './ui'
import PhoneInput from '../../components/PhoneInput'

interface ClientRow {
  id: string; name: string; segment: string | null; billing_cycle: 'weekly' | 'fortnightly' | 'monthly' | 'per_trip'; tally_ledger: string | null
  contact_name: string | null; contact_phone: string | null; email: string | null; gstin: string | null; language: 'en' | 'hi' | 'mr'; is_active: boolean; trips: number
}
interface Invite { email_status: string; email_error: string | null; link: string | null }
interface Login { id: string; name: string; email: string; is_active: boolean; must_change_password: boolean }

export default function ClientsTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useI18n()
  const [rows, setRows] = useState<ClientRow[] | null>(null)
  const [error, setError] = useState(false)
  const [showOff, setShowOff] = useState(false)
  const { values: f, set, clear, active } = useFilters({ q: '', cycle: '' })
  const [form, setForm] = useState<ClientRow | 'new' | null>(null)
  const [logins, setLogins] = useState<ClientRow | null>(null)
  const load = () => api<ClientRow[]>('/setup/clients').then(setRows).catch(() => setError(true))
  useEffect(() => { void load() }, [])
  if (error) return <p className="text-bad">{t('setup.loadFail')}</p>
  if (!rows) return <p className="text-muted">{t('common.loading')}</p>
  const base = rows.filter((c) => showOff || c.is_active)
  const shown = base.filter((c) => hit(f.q, c.name, c.contact_name, c.contact_phone, c.email, c.gstin, c.tally_ledger, c.segment) && (!f.cycle || c.billing_cycle === f.cycle))
  const selects: FilterSelect[] = [{ key: 'cycle', label: t('setup.client.cycle'), value: f.cycle, onChange: (v) => set('cycle', v), options: [
    ['', t('filter.allCycles')], ...[...new Set(base.map((c) => c.billing_cycle))].sort().map((c): [string, string] => [c, `${t(`setup.cycle.${c}`)} (${base.filter((x) => x.billing_cycle === c).length})`])] }]
  return (
    <div className="space-y-4">
      <FilterBar q={f.q} onQ={(v) => set('q', v)} placeholder={t('filter.clients')} selects={selects} shown={shown.length} total={base.length} active={active} onClear={clear} />
      {shown.length === 0 && rows.length > 0 && <NoMatch onClear={clear} />}
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
            <td className="px-4 py-3 text-right"><span className="inline-flex gap-2">{canEdit && <button onClick={() => setLogins(c)} className={`${btnGhost} inline-flex items-center gap-1.5`}><KeyRound size={14} aria-hidden /> {t('setup.portal.manage')}</button>}{canEdit && <button onClick={() => setForm(c)} className={`${btnGhost} inline-flex items-center gap-1.5`}><Pencil size={14} aria-hidden /> {t('setup.edit')}</button>}</span></td>
          </tr>
        ))}
      </Table>
      {logins && <LoginsDialog client={logins} onClose={() => setLogins(null)} />}
      {form && <ClientForm client={form === 'new' ? null : form} onClose={() => setForm(null)} onSaved={() => { setForm(null); void load() }} />}
    </div>
  )
}

function ClientForm({ client, onClose, onSaved }: { client: ClientRow | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n()
  const [f, setF] = useState({
    name: client?.name ?? '', segment: client?.segment ?? '', billing_cycle: client?.billing_cycle ?? 'weekly', tally_ledger: client?.tally_ledger ?? '',
    contact_name: client?.contact_name ?? '', contact_phone: client?.contact_phone ?? '', email: client?.email ?? '', gstin: client?.gstin ?? '', language: client?.language ?? 'en', is_active: client?.is_active ?? true,
  })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  async function save() {
    const body = JSON.stringify({ ...f, segment: f.segment || null, tally_ledger: f.tally_ledger || null, contact_name: f.contact_name || null, contact_phone: f.contact_phone || null, email: f.email.trim() || null, gstin: f.gstin || null, ...(client ? {} : { is_active: undefined }) })
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
        <PhoneInput label={t('setup.client.phone')} value={f.contact_phone} onChange={(v) => setF({ ...f, contact_phone: v })} />
      </div>
      <Field label={t('setup.client.email')} hint={t('setup.client.emailHint')}><input className={inputCls} type="email" maxLength={160} value={f.email} onChange={set('email')} /></Field>
      <Field label={t('setup.client.lang')}>
        <select className={inputCls} value={f.language} onChange={set('language')}>
          <option value="en">English</option><option value="hi">हिन्दी</option><option value="mr">मराठी</option>
        </select>
      </Field>
      {client && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> {t('setup.active')}</label>}
    </FormModal>
  )
}

/** The people at a client who may sign in to see its shipments. The ops head makes each one; the temporary password is shown once. */
function LoginsDialog({ client, onClose }: { client: ClientRow; onClose: () => void }) {
  const { t } = useI18n()
  const [rows, setRows] = useState<Login[] | null>(null)
  const [f, setF] = useState({ name: '', email: '' })
  const [note, setNote] = useState<{ email: string; link: string | null; why: string | null } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { busy, run } = useBusy()
  const load = () => api<Login[]>(`/setup/clients/${client.id}/portal`).then(setRows).catch(() => setError(t('setup.loadFail')))
  useEffect(() => { void load() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : t('setup.loadFail'))

  const add = (e: { preventDefault(): void }) => { e.preventDefault(); return run('add', send) }
  async function send() {
    setError(null); setNote(null)
    try { const r = await api<Invite>(`/setup/clients/${client.id}/portal`, { method: 'POST', body: JSON.stringify({ ...f, language: client.language }) }); setNote({ email: f.email, link: r.link, why: r.email_error }); setF({ name: '', email: '' }); await load() } catch (err) { fail(err) }
  }
  const reset = (u: Login) => run(`reset-${u.id}`, () => resetPw(u))
  async function resetPw(u: Login) {
    setError(null); setNote(null)
    try { const r = await api<Invite>(`/setup/clients/${client.id}/portal/${u.id}/reset-password`, { method: 'POST' }); setNote({ email: u.email, link: r.link, why: r.email_error }) } catch (err) { fail(err) }
  }
  const toggle = (u: Login) => run(`toggle-${u.id}`, () => flip(u))
  async function flip(u: Login) {
    setError(null)
    try { await api(`/setup/clients/${client.id}/portal/${u.id}`, { method: 'PATCH', body: JSON.stringify({ is_active: !u.is_active }) }); await load() } catch (err) { fail(err) }
  }

  return (
    <Modal title={t('setup.portal.title', { name: client.name })} onClose={onClose} wide>
      <p className="text-sm text-muted">{t('setup.portal.help')} {t('setup.portal.created')}</p>
      {note && (note.link
        ? <p role="status" className="rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn">{t('setup.portal.notsent', { why: note.why ?? '-' })} <b className="select-all break-all font-mono">{note.link}</b></p>
        : <p role="status" className="rounded-lg bg-ok-soft px-3 py-2 text-sm text-ok">{t('setup.portal.sent', { email: note.email })}</p>)}
      {rows && (rows.length === 0 ? <p className="text-sm text-muted">{t('setup.portal.none')}</p> : (
        <ul className="divide-y divide-line rounded-xl border border-line text-sm">
          {rows.map((u) => (
            <li key={u.id} className={`flex flex-wrap items-center gap-3 px-3 py-2.5 ${u.is_active ? '' : 'text-muted'}`}>
              <span className="min-w-0 flex-1"><b className="font-medium">{u.name}</b> <span className="text-muted">{u.email}</span></span>
              <button disabled={!!busy} onClick={() => void reset(u)} className={`${btnGhost} disabled:opacity-60`}>{busy === `reset-${u.id}` ? <><Spin />{t('common.sending')}</> : t('setup.portal.reset')}</button>
              <button disabled={!!busy} onClick={() => void toggle(u)} className={`${btnGhost} disabled:opacity-60`}>{busy === `toggle-${u.id}` && <Spin />}{t(u.is_active ? 'setup.portal.off' : 'setup.portal.on')}</button>
            </li>
          ))}
        </ul>
      ))}
      <form onSubmit={(e) => void add(e)} className="grid gap-3 border-t border-line pt-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <Field label={t('setup.portal.name')}><input className={inputCls} required minLength={2} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label={t('setup.portal.email')}><input className={inputCls} type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <button disabled={!!busy} className={btnPrimary}>{busy === 'add' ? <><Spin />{t('common.sending')}</> : t('setup.portal.add')}</button>
      </form>
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
    </Modal>
  )
}
