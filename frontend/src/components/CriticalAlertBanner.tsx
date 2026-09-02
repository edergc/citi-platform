import { Link } from 'react-router-dom'
import { AlertOctagon } from 'lucide-react'
import { useCriticalAlerts } from '@/lib/useCriticalAlerts'

export function CriticalAlertBanner() {
  const { items } = useCriticalAlerts()
  if (items.length === 0) return null

  // Prefer /alerts (has per-rule detail) whenever a threshold breach is in the mix;
  // /connectivity only when every item here is a server disconnect — either way this
  // lands on a page that actually shows what's currently critical, not a dead end.
  const target = items.some((i) => i.kind === 'threshold') ? '/alerts?severity=critical' : '/connectivity'

  return (
    <Link
      to={target}
      className="flex items-center justify-center gap-2 border-b border-red-900 bg-red-950/80 px-4 py-2 text-sm text-red-200 transition-colors hover:bg-red-950"
    >
      <AlertOctagon className="h-4 w-4 shrink-0 text-red-400" />
      <span>{items.length === 1 ? '1 alerta crítica sin reconocer' : `${items.length} alertas críticas sin reconocer`}</span>
      <span className="font-medium underline underline-offset-2">Ver alertas →</span>
    </Link>
  )
}
