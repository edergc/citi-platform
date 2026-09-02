import type { ServerHealth } from '@/types'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const healthConfig: Record<ServerHealth, { label: string; variant: 'success' | 'warning' | 'danger'; dot: string }> = {
  ok: { label: 'Va bien', variant: 'success', dot: 'bg-emerald-400' },
  warning: { label: 'Atención', variant: 'warning', dot: 'bg-amber-400' },
  critical: { label: 'Necesita revisión', variant: 'danger', dot: 'bg-red-400' },
}

export function HealthBadge({
  health,
  reasons,
  className,
}: {
  health: ServerHealth
  reasons: string[]
  className?: string
}) {
  const config = healthConfig[health]
  const title = reasons.length > 0 ? reasons.join(' · ') : 'Sin problemas detectados'

  return (
    <Badge variant={config.variant} className={cn('inline-flex items-center gap-1.5', className)} title={title}>
      <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', config.dot)} />
      {config.label}
    </Badge>
  )
}
