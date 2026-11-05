import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import BranchesTab from './setup/BranchesTab'
import ClientsTab from './setup/ClientsTab'
import DriversTab from './setup/DriversTab'
import MessagesTab from './setup/MessagesTab'
import StaffTab from './setup/StaffTab'
import TestDataTab from './setup/TestDataTab'
import TrucksTab from './setup/TrucksTab'
import VendorsTab from './setup/VendorsTab'

const TABS = ['drivers', 'trucks', 'clients', 'vendors', 'branches', 'messages', 'reset', 'staff'] as const
type Tab = (typeof TABS)[number]

/** Everything trips are built from: drivers, trucks, clients, hired vendors, and (admin only) office staff. */
export default function Setup() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const isAdmin = user?.role === 'admin'
  const canEdit = user?.role === 'ops' || isAdmin
  const [devMode, setDevMode] = useState(false)
  useEffect(() => { if (canEdit) api('/devtools/test-data').then(() => setDevMode(true)).catch(() => setDevMode(false)) }, [canEdit])
  const tabs = TABS.filter((x) => (x !== 'staff' || isAdmin) && (x !== 'reset' || devMode)) // the reset tab exists only on a development server
  const raw = params.get('tab')
  const tab: Tab = (tabs as readonly string[]).includes(raw ?? '') ? (raw as Tab) : 'drivers'

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">{t('setup.title')}</h1>
        <p className="text-sm text-muted">{t('setup.sub')}</p>
        {!canEdit && <p className="mt-1 text-sm text-warn">{t('setup.canRead')}</p>}
      </div>
      <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-line">
        {tabs.map((x) => (
          <button key={x} role="tab" aria-selected={tab === x} onClick={() => setParams({ tab: x })}
            className={`whitespace-nowrap border-b-2 px-4 py-2 text-sm ${tab === x ? 'border-ink font-medium text-ink' : 'border-transparent text-muted hover:text-ink'}`}>
            {t(`setup.tab.${x}`)}
          </button>
        ))}
      </div>
      {tab === 'drivers' && <DriversTab canEdit={canEdit} />}
      {tab === 'trucks' && <TrucksTab canEdit={canEdit} />}
      {tab === 'clients' && <ClientsTab canEdit={canEdit} />}
      {tab === 'vendors' && <VendorsTab canEdit={canEdit} />}
      {tab === 'branches' && <BranchesTab canEdit={canEdit} />}
      {tab === 'messages' && <MessagesTab />}
      {tab === 'reset' && <TestDataTab />}
      {tab === 'staff' && isAdmin && <StaffTab />}
    </div>
  )
}
