import { Copy, MessageCircle } from 'lucide-react'
import { useState } from 'react'
import { useI18n } from '../../lib/i18n'
import { btnGhost, btnPrimary, Modal } from './ui'

export interface Invite { url: string; status: 'sent' | 'simulated' | 'failed' | 'skipped'; error: string | null; provider: string; text: string; whatsapp_link: string | null }

/** After registering a driver (or sending the link again): what happened to the WhatsApp message, the link to hand over if it did not arrive, and the backup PIN. */
export default function InviteDialog({ name, pin, invite, onClose }: { name: string; pin: string | null; invite: Invite; onClose: () => void }) {
  const { t } = useI18n()
  const [copied, setCopied] = useState(false)
  const tone = invite.status === 'sent' ? 'bg-ok-soft text-ok' : invite.status === 'failed' ? 'bg-bad-soft text-bad' : 'bg-warn-soft text-warn'
  async function copy() {
    try { await navigator.clipboard.writeText(invite.url); setCopied(true) } catch { setCopied(false) }
  }
  return (
    <Modal title={t('setup.drv.pinTitle', { name })} onClose={onClose} wide>
      <p role="status" className={`rounded-lg px-3 py-2 text-sm ${tone}`}>{t(`notif.st.${invite.status}`, { name, error: invite.error ?? '' })}</p>
      <div className="space-y-2">
        <p className="text-sm font-medium">{t('notif.link')}</p>
        <input readOnly value={invite.url} aria-label={t('notif.link')} onFocus={(e) => e.currentTarget.select()} className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-xs" />
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => void copy()} className={`${btnGhost} inline-flex items-center gap-1.5`}><Copy size={14} aria-hidden /> {copied ? t('notif.copied') : t('notif.copy')}</button>
          {invite.whatsapp_link && <a href={invite.whatsapp_link} target="_blank" rel="noreferrer" className={`${btnGhost} inline-flex items-center gap-1.5`}><MessageCircle size={14} aria-hidden /> {t('notif.openWa')}</a>}
        </div>
      </div>
      {pin && (
        <div className="space-y-2">
          <p className="text-sm text-muted">{t('notif.pinFallback', { name })}</p>
          <p className="select-all break-all rounded-xl bg-wash p-4 text-center text-3xl font-semibold tabular-nums tracking-wider" aria-label="One-time secret">{pin}</p>
        </div>
      )}
      <div className="flex justify-end"><button onClick={onClose} className={btnPrimary}>{t('setup.close')}</button></div>
    </Modal>
  )
}
