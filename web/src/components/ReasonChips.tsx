import { useI18n, type Key } from '../lib/i18n'

const LABEL: Record<string, string> = {
  shortage_or_damage: 'Shortage / damage remark',
  low_confidence: 'Low AI confidence',
  quantity_mismatch: 'Quantity differs from the booking',
  quantity_not_read: 'Quantity not found on the receipt',
  quantity_unclear: 'Several goods or units: check the quantity',
  date_missing: 'Delivery date not read',
  gps_missing: 'Photo has no location',
  far_from_destination: 'Taken far from the destination',
  retake_cap_reached: 'Driver already retook twice',
  ai_unavailable: 'AI was unavailable',
  stamp_missing: 'Stamp not visible',
  signature_missing: 'Signature not visible',
  lr_mismatch: 'LR number does not match',
  unreadable: 'Photo unreadable',
  not_a_pod: 'Does not look like a POD',
}

export const reasonLabel = (r: string) => LABEL[r] ?? r.replaceAll('_', ' ')

export function ReasonChips({ reasons }: { reasons: string[] }) {
  const { t } = useI18n()
  return (
    <div className="flex flex-wrap gap-1.5">
      {reasons.map((r) => (
        <span key={r} className="rounded-full bg-warn-soft px-2.5 py-1 text-xs font-medium text-warn">{r in LABEL ? t(`reason.${r}` as Key) : reasonLabel(r)}</span>
      ))}
    </div>
  )
}
