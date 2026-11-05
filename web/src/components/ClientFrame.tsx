import { Truck } from 'lucide-react'
import type { ReactNode } from 'react'

/** The frame of the pages a client opens from a link (delivery proof, tracking): our brand, then the content, then a quiet footer. */
export default function ClientFrame({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className="min-h-full">
      <header className="border-b border-line">
        <div className="mx-auto flex h-14 max-w-3xl items-center gap-2.5 px-4 text-base font-semibold tracking-tight sm:px-6">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-ink text-surface"><Truck size={15} aria-hidden /></span> CargoOne
        </div>
      </header>
      <main className={`mx-auto max-w-3xl px-4 py-10 sm:px-6 ${className}`}>{children}</main>
    </div>
  )
}
