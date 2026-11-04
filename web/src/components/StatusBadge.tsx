import { CircleCheck, Clock, Eye, FileCheck2, RotateCcw, XCircle, type LucideIcon } from 'lucide-react'
import type { PodStatus } from '../lib/api'
import { useI18n } from '../lib/i18n'

const MAP: Record<PodStatus, { label: string; icon: LucideIcon; cls: string }> = {
  pending: { label: 'Awaiting POD', icon: Clock, cls: 'bg-wash text-muted' },
  uploaded: { label: 'Checking', icon: Clock, cls: 'bg-accent-soft text-accent' },
  verified: { label: 'Verified', icon: CircleCheck, cls: 'bg-ok-soft text-ok' },
  needs_review: { label: 'Needs review', icon: Eye, cls: 'bg-warn-soft text-warn' },
  retake_requested: { label: 'Retake', icon: RotateCcw, cls: 'bg-warn-soft text-warn' },
  rejected: { label: 'Rejected', icon: XCircle, cls: 'bg-bad-soft text-bad' },
  billed: { label: 'Billed', icon: FileCheck2, cls: 'bg-accent-soft text-accent' },
}

export function StatusBadge({ status }: { status: PodStatus }) {
  const { t } = useI18n()
  const { label, icon: Icon, cls } = MAP[status]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${cls}`}>
      <Icon size={14} aria-hidden /> {t(`status.${status}`) || label}
    </span>
  )
}

export const statusIcon = (s: PodStatus) => MAP[s]
