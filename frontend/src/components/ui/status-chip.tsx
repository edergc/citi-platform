import { type ReactNode } from 'react'
import { cn } from '@/lib/utils'

const toneClass = {
  critical: 'bg-red-500 text-red-950',
  warning: 'bg-amber-500 text-amber-950',
  info: 'bg-sky-500 text-sky-950',
  ok: 'bg-emerald-500 text-emerald-950',
  neutral: 'bg-slate-600 text-slate-100',
}

/** Checkmk's solid CRIT/WARN/OK chip — opaque and bold, deliberately higher-contrast
 * than the app's existing translucent Badge (kept as-is everywhere else; this is just
 * for the monitoring-dashboard-style pages modeled on the Checkmk reference). */
export function StatusChip({ tone, children, className }: { tone: keyof typeof toneClass; children: ReactNode; className?: string }) {
  return (
    <span className={cn('inline-flex items-center rounded px-2 py-0.5 text-xs font-bold', toneClass[tone], className)}>
      {children}
    </span>
  )
}
