const LABEL: Record<string, string> = {
  shortage_or_damage: 'Shortage / damage remark',
  low_confidence: 'Low AI confidence',
  date_missing: 'Delivery date not read',
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
  return (
    <div className="flex flex-wrap gap-1.5">
      {reasons.map((r) => (
        <span key={r} className="rounded-full bg-warn-soft px-2.5 py-1 text-xs font-medium text-warn">{reasonLabel(r)}</span>
      ))}
    </div>
  )
}
