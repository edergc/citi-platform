import type { ServerHealth, ServerStatus } from '@/types'

export const ALL_SITES = '__all__'
export const ALL_HEALTH = '__all__'
export const ALL_USAGE = '__all__'

export const healthFilterLabel: Record<ServerHealth, string> = {
  ok: 'Va bien',
  warning: 'Atención',
  critical: 'Necesita revisión',
}

// Same hues as HealthBadge's dot (emerald-400 / amber-400 / red-400) so the donut
// reads as the same signal wherever it shows up in the app.
export const HEALTH_COLORS: Record<ServerHealth, string> = {
  ok: '#34d399',
  warning: '#fbbf24',
  critical: '#f87171',
}

// Same states as ServerStatus, mapped to StatusChip's solid-pill tones instead of
// Badge's translucent ones — for the Checkmk-styled pages (Servidores Lista/Resumen).
export const statusTone: Record<ServerStatus, 'ok' | 'critical' | 'warning' | 'neutral'> = {
  online: 'ok',
  offline: 'critical',
  degraded: 'warning',
  unknown: 'neutral',
}

export const statusLabel: Record<ServerStatus, string> = {
  online: 'En línea',
  offline: 'Desconectado',
  degraded: 'Degradado',
  unknown: 'Sin datos',
}

export const severityVariant: Record<string, 'info' | 'warning' | 'danger'> = {
  info: 'info',
  warning: 'warning',
  critical: 'danger',
}

export const severityLabel: Record<string, string> = {
  info: 'Informativo',
  warning: 'Advertencia',
  critical: 'Crítico',
}
